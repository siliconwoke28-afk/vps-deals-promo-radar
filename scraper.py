# ::ILANG
# ::MODULE{SCRAPER|role:读取I-Lang 从公开官方页确定性提取证据}
# ::BOUNDARY{never:绕robots 绕TLS 编价格 将失败来源标记成功}
"""Conservative public-page collector. No packages, keys, browser or inference."""
import argparse
import hashlib
import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlsplit, urljoin
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
from config import ROOT, load_config, slug, safe_url

def utcnow(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style','noscript','template'): self.skip += 1
    def handle_endtag(self, tag):
        if tag in ('script','style','noscript','template'): self.skip=max(0,self.skip-1)
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

def visible_text(html):
    parser=VisibleText(); parser.feed(html)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()

def public_url(url, hosts):
    safe_url(url); host=urlsplit(url).hostname
    if host not in hosts: raise ValueError('Redirect outside configured official hosts')
    for result in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ValueError('Non-public address refused')

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

class Fetcher:
    def __init__(self, policy, hosts):
        self.policy=policy; self.hosts=hosts; self.robots={}; self.last={}
        self.opener=build_opener(NoRedirect())
    def request(self, url, robots=False, depth=0):
        if depth>4: raise ValueError('Too many redirects')
        public_url(url,self.hosts)
        host=urlsplit(url).netloc
        if not robots:
            rp=self.robot_rules(url)
            if not rp.can_fetch(self.policy['user_agent'],url): raise ValueError('robots.txt disallows this page')
            delay=max(1,rp.crawl_delay(self.policy['user_agent']) or rp.crawl_delay('*') or 0)
            rate=rp.request_rate(self.policy['user_agent']) or rp.request_rate('*')
            if rate: delay=max(delay,rate.seconds/rate.requests)
            if delay>120: raise ValueError('Crawl delay too high for this collector')
            time.sleep(max(0,delay-(time.monotonic()-self.last.get(host,0))))
        headers={'User-Agent':self.policy['user_agent'],'Accept-Language':'en-US,en;q=0.8','Accept':'text/html,text/plain;q=0.9'}
        try:
            with self.opener.open(Request(url,headers=headers),timeout=self.policy['timeout_seconds']) as response:
                data=response.read(self.policy['max_bytes']+1)
                if len(data)>self.policy['max_bytes']: raise ValueError('Source exceeds byte limit')
                mime=response.headers.get_content_type()
                if mime not in ('text/html','text/plain','application/xhtml+xml'): raise ValueError('Unexpected source content type')
                charset=response.headers.get_content_charset() or 'utf-8'
                self.last[host]=time.monotonic()
                return data.decode(charset,'replace'),url
        except HTTPError as exc:
            if exc.code in (301,302,303,307,308):
                target=urljoin(url,exc.headers['Location'])
                return self.request(target,robots,depth+1)
            raise
    def robot_rules(self,url):
        p=urlsplit(url); origin=f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            try: text,_=self.request(origin+'/robots.txt',robots=True)
            except HTTPError as exc:
                if exc.code not in (404,410): raise
                text=''
            rp=RobotFileParser();rp.parse(text.splitlines());self.robots[origin]=rp
        return self.robots[origin]

def extract(provider, rule, html, fetched_at, final_url):
    if not rule: return []
    text=visible_text(html); offers=[]; seen=set()
    for match in re.finditer(rule['pattern'],text):
        fields={k:v for k,v in match.groupdict().items() if v is not None}
        title=fields.get('title','').strip()
        if not title or title in seen: continue
        try: price=Decimal(fields['price'])
        except (KeyError,InvalidOperation): continue
        if not price.is_finite() or price<0 or price>100000: continue
        seen.add(title)
        offer={'id':provider['id']+'-'+slug(title),'provider':provider['id'],
            'title':title,'price':format(price,'.2f'),'currency':rule['currency'],
            'offer_url':provider['source_url'],'source_url':final_url,'fetched_at':fetched_at,
            'kind':rule['kind'],'billing':rule['billing'],'price_label':rule['price_label'],
            'note':rule['note'],'evidence':match.group(0),
            'source_sha256':hashlib.sha256(html.encode('utf-8')).hexdigest()}
        for field in ('terms','cpu','ram','storage','renewal','discount','valid_until'):
            if field in fields:offer[field]=fields[field]
        if offer.get('valid_until') and offer['valid_until'] < fetched_at[:10]: continue
        offers.append(offer)
    return offers

def collect(config):
    hosts={urlsplit(p[key]).hostname for p in config['providers'] for key in ('source_url','website')}
    fetcher=Fetcher(config['policy'],hosts); offers=[]; states=[]
    for provider in config['providers']:
        state={'provider':provider['id'],'attempted_at':utcnow(),'source_url':provider['source_url']}
        try:
            html,url=fetcher.request(provider['source_url'])
            found=extract(provider,config['extractors'].get(provider['id']),html,utcnow(),url)
            offers.extend(found)
            state.update(status='verified' if found else 'no_verified_offer',offer_count=len(found),
                message='Official page parsed' if found else 'No unambiguous priced offer matched; no price published')
        except Exception as exc:
            state.update(status='unavailable',offer_count=0,message=f'{type(exc).__name__}: {exc}')
        states.append(state)
        print(f"{provider['name']}: {state['status']} ({state['offer_count']})",flush=True)
    return {'generated_at':utcnow(),'offers':offers,'sources':states}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config');args=parser.parse_args()
    config=load_config(args.config); data=collect(config)
    target=ROOT/'data/offers.json'; target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');temp.replace(target)
    # Publish the empty/partial truth even on failure; CI reports a failure after committing it.
    return 0 if data['offers'] else 2

if __name__=='__main__': raise SystemExit(main())
