# ::ILANG
# ::MODULE{BUILD|role:读取I-Lang与采集数据 生成静态HTML和索引文件}
# ::BOUNDARY{never:补价格 编有效期 把失效快照当当前优惠}
"""Deterministic, dependency-free static generator."""
import argparse
import hashlib
import html
import json
import re
import shutil
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from string import Template
from xml.sax.saxutils import escape as xml_escape
from config import ROOT, load_config, safe_url

def esc(value): return html.escape(str(value),quote=True)
def stamp(value): return datetime.fromisoformat(value.replace('Z','+00:00'))
def human_time(value): return stamp(value).strftime('%d %b %Y, %H:%M UTC')
def json_script(value): return json.dumps(value,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
def template(name, **values):
    return Template((ROOT/'templates'/name).read_text(encoding='utf-8')).substitute(values)

def current_offers(config,data,now):
    providers={p['id']:p for p in config['providers']}; result=[]; seen=set()
    for offer in data['offers']:
        if offer['provider'] not in providers: continue
        provider=providers[offer['provider']]
        # A changed source in I-Lang invalidates that provider's old snapshot.
        if offer['offer_url']!=provider['source_url']: continue
        if offer['id'] in seen: raise ValueError('Duplicate offer ID')
        if not re.fullmatch(r'[a-z0-9-]+',offer['id']): raise ValueError('Unsafe offer ID')
        seen.add(offer['id'])
        age=now-stamp(offer['fetched_at'])
        if age<timedelta(minutes=-5) or age>timedelta(hours=config['policy']['max_age_hours']): continue
        if offer.get('valid_until'):
            expiry=offer['valid_until']
            if len(expiry)==10:
                if expiry<now.date().isoformat(): continue
            elif stamp(expiry)<now: continue
        if offer.get('currency')!=config['site']['currency']: continue
        if 'price' not in offer:
            if config['policy']['allow_unpriced']: raise ValueError('Unpriced rendering is not implemented')
            continue
        price=Decimal(str(offer['price']))
        if not price.is_finite() or price<0: raise ValueError('Invalid price')
        if not offer.get('evidence') or not offer.get('source_sha256'): raise ValueError('Price lacks evidence')
        safe_url(offer['source_url']);safe_url(offer['offer_url'])
        result.append(offer)
    if config['policy']['sort']=='provider':
        result.sort(key=lambda o:(o['provider'],Decimal(o['price']),o['title']))
    else: raise ValueError('Unsupported sort configuration')
    return result

def offer_schema(offer,provider):
    result={'@type':'Offer','name':offer['title'],'url':offer['offer_url'],
        'seller':{'@type':'Organization','name':provider['name']},
        'price':offer['price'],'priceCurrency':offer['currency'],
        'priceSpecification':{'@type':'UnitPriceSpecification','price':offer['price'],
            'priceCurrency':offer['currency'],'unitText':'MONTH','description':offer['price_label']},
        'description':offer.get('terms',offer['note'])}
    # A published plan is not evidence of stock or an expiry. Never invent them.
    if offer.get('availability'): result['availability']=offer['availability']
    if offer.get('valid_until'):result['priceValidUntil']=offer['valid_until'][:10]
    return result

def item_list(offers,domain):
    return {'@type':'ItemList','numberOfItems':len(offers),'itemListElement':[
        {'@type':'ListItem','position':i+1,'url':domain+'/deals/'+o['id']+'/','name':o['title']} for i,o in enumerate(offers)]}

def breadcrumb(items):
    return {'@type':'BreadcrumbList','itemListElement':[
        {'@type':'ListItem','position':i+1,'name':name,'item':url} for i,(name,url) in enumerate(items)]}

def render_row(offer,provider):
    terms=offer.get('terms') or offer['note']
    kind='Promotion' if offer['kind']=='promotion' else 'Standard rate'
    discount=f" · {esc(offer['discount'])}% advertised" if offer.get('discount') else ''
    resources=f"{esc(offer.get('cpu','Not stated'))} vCPU · {esc(offer.get('ram','Not stated'))} GB RAM"
    return f'''<tr data-provider="{esc(provider['id'])}" data-kind="{esc(offer['kind'])}"><td><a class="provider-name" href="/providers/{provider['id']}/">{esc(provider['name'])}</a><a class="plan-name" href="/deals/{offer['id']}/">{esc(offer['title'])}</a><span class="badge">{kind}{discount}</span></td><td class="resources">{resources}<span>{esc(offer.get('storage','Not stated'))} GB storage</span></td><td><span class="rate">${esc(offer['price'])}<small> / mo</small></span><div class="small">USD · {esc(offer['price_label'])}</div></td><td class="terms">{esc(terms)}</td><td><a class="details-link" href="/deals/{offer['id']}/" aria-label="View {esc(provider['name'])} {esc(offer['title'])}">View offer →</a></td></tr>'''

def workflow_text(config):
    cron=config['policy']['cron']
    if not re.fullmatch(r'[\d*/ ,\-]+',cron) or len(cron.split())!=5:raise ValueError('Invalid cron')
    return '''# Generated from .ilang/site.ilang by build.py --sync-workflow.
name: Refresh official VPS offers
on:
  schedule:
    - cron: "'''+cron+'''"
  workflow_dispatch:
  push:
    branches: [main]
    paths: ['**.py', 'templates/**', 'assets/**', '.ilang/**', 'tests/**', '.github/workflows/update.yml']
permissions:
  contents: write
concurrency:
  group: vps-offer-refresh
  cancel-in-progress: false
jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 12
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Test truth and configuration contracts
        run: python -m unittest discover -s tests -v
      - name: Collect official sources
        id: scrape
        continue-on-error: true
        run: python scraper.py
      - name: Render truthful snapshot (including source failures)
        run: python build.py
      - name: Verify generated pages
        run: python verify.py
      - name: Commit dated snapshot
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/offers.json site/
          if ! git diff --cached --quiet; then
            git commit -m "data: refresh official VPS source snapshot"
            git push
          fi
      - name: Report source coverage
        run: python verify.py --health
'''

def build(config,data,output=None,now=None):
    now=now or datetime.now(timezone.utc); out=Path(output or ROOT/'site').resolve()
    if out.exists():
        if out!=(ROOT/'site').resolve(): raise ValueError('Refuse to clear a non-default output directory')
        shutil.rmtree(out)
    out.mkdir(parents=True)
    brand=config['site']['brand'];domain=config['site']['domain'].rstrip('/')
    providers={p['id']:p for p in config['providers']}
    offers=current_offers(config,data,now)
    fetched=max((o['fetched_at'] for o in offers),default=data['generated_at'])
    month=stamp(fetched).strftime('%B %Y'); updated=human_time(fetched)
    attempts={s['provider']:s for s in data.get('sources',[])}; sitemap=[]
    shared=dict(brand=esc(brand),domain=esc(domain),repository=esc(config['site']['repository']),updated=esc(updated))
    common=dict(collected=esc(fetched),max_age=config['policy']['max_age_hours'],updated=esc(updated))
    empty='<div class="empty"><h2>No current verified prices</h2><p>We could not verify prices in this snapshot. Visit the official source; we will not fill gaps with estimates.</p></div>'
    def page(path,title,description,content,schemas=None,lastmod=fetched,index=True):
        target=out/(path.strip('/')+'/index.html' if path.strip('/') else 'index.html');target.parent.mkdir(parents=True,exist_ok=True)
        graph={'@context':'https://schema.org','@graph':schemas or []}
        target.write_text(template('base.html',title=esc(title),description=esc(description),canonical=esc(domain+path),robots='index,follow' if index else 'noindex,follow',content=content,jsonld=json_script(graph),**shared),encoding='utf-8')
        if index:sitemap.append((domain+path,lastmod))
    def rows(items):return ''.join(render_row(o,providers[o['provider']]) for o in items)
    required={'index','provider','deal','compare'}
    if not required.issubset(config['policy']['render']): raise ValueError('v1 requires index/provider/deal/compare render rules')
    content=template('index.html',offer_count=len(offers),provider_count=len(providers),rows=rows(offers),
        schedule_label=esc('every '+config['policy']['cron'].split()[1][2:]+' hours' if config['policy']['cron'].split()[1].startswith('*/') else config['policy']['cron']+' UTC'),provider_options=''.join(f'<option value="{p["id"]}">{esc(p["name"])}</option>' for p in providers.values()),empty='' if offers else empty,**common)
    page('/',f'{brand}: official VPS offers and prices | {month}',f'Compare {len(offers)} published VPS plans with contract terms and official source evidence. Updated {month}.',content,[item_list(offers,domain)])
    for pid,p in providers.items():
        selected=[o for o in offers if o['provider']==pid];source=attempts.get(pid,{})
        status=(f'{len(selected)} priced plans verified. Snapshot: {updated}.' if selected else 'No current verified prices. Check the official provider page.')
        summary=f'Published prices and conditions from {p["name"]}. Independently collected; not a provider endorsement.'
        crumbs=f'<div class="breadcrumbs"><a href="/">All offers</a> / {esc(p["name"])}</div>'
        content=template('provider.html',provider_name=esc(p['name']),summary=esc(summary),source_url=esc(p['source_url']),status=esc(status),breadcrumbs=crumbs,rows=rows(selected),empty='' if selected else empty,**common)
        schema={'@type':'Service','name':p['name']+' VPS hosting','provider':{'@type':'Organization','name':p['name'],'url':p['website']}}
        if selected:
            schema['offers']={'@type':'AggregateOffer','lowPrice':min(selected,key=lambda o:Decimal(o['price']))['price'],
                'highPrice':max(selected,key=lambda o:Decimal(o['price']))['price'],'priceCurrency':config['site']['currency'],
                'offerCount':len(selected),'offers':[offer_schema(o,p) for o in selected]}
        path='/providers/'+pid+'/'
        page(path,f'{p["name"]} VPS prices and offers | {month}',summary+' '+month,content,[schema,breadcrumb([('All offers',domain+'/'),(p['name'],domain+path)])],index=bool(selected))
    for o in offers:
        p=providers[o['provider']];kind='Promotion' if o['kind']=='promotion' else 'Standard rate'
        terms=o.get('terms') or 'Term and renewal price not unambiguously stated in the captured offer. Confirm at checkout.'
        discount=f'<p class="badge">{esc(o["discount"])}% off as advertised by provider</p>' if o.get('discount') else ''
        crumbs=f'<div class="breadcrumbs"><a href="/">All offers</a> / <a href="/providers/{p["id"]}/">{esc(p["name"])}</a> / {esc(o["title"])}</div>'
        content=template('deal.html',breadcrumbs=crumbs,provider_name=esc(p['name']),kind=kind,plan_title=esc(o['title']),
            price_label=esc(o['price_label']),specs=''.join(f'<div><strong>{esc(o.get(k,"Not stated"))}{unit}</strong><span>{label}</span></div>' for k,unit,label in [('cpu','','vCPU'),('ram',' GB','Memory'),('storage',' GB','Storage')]),
            terms=esc(terms),note=esc(o['note']),expiry=esc('Expires '+o['valid_until'] if o.get('valid_until') else 'No expiry date was published in the captured offer. Availability can change.'),
            evidence=esc(o['evidence']),source_url=esc(o['source_url']),source_hash=esc(o['source_sha256']),price=esc(o['price']),discount=discount,
            outbound=esc(p['affiliate_url'] or o['offer_url']),rel='sponsored noopener' if p['affiliate_url'] else 'noopener',
            link_disclosure='Affiliate link: we may earn a commission.' if p['affiliate_url'] else 'Direct official link. No affiliate tracking has been added.',
            collected=esc(o['fetched_at']),max_age=config['policy']['max_age_hours'],updated=esc(human_time(o['fetched_at'])))
        path='/deals/'+o['id']+'/'
        schema={'@type':'Service','name':p['name']+' '+o['title'],'serviceType':'VPS hosting','offers':offer_schema(o,p)}
        discount_title=f' · {o["discount"]}% advertised discount' if o.get('discount') else ''
        page(path,f'{p["name"]} {o["title"]}: ${o["price"]}/mo{discount_title} | {month}',f'{p["name"]} {o["title"]} advertised at USD {o["price"]}/month. {terms} Verified {month}.',content,[schema,breadcrumb([('All offers',domain+'/'),(p['name'],domain+'/providers/'+p['id']+'/'),(o['title'],domain+path)])],lastmod=o['fetched_at'])
    comparison=''.join(f'<tr><td><a class="provider-name" href="/providers/{o["provider"]}/">{esc(providers[o["provider"]]["name"])}</a><a class="plan-name" href="/deals/{o["id"]}/">{esc(o["title"])}</a></td><td>{esc(o.get("cpu","Not stated"))}</td><td>{esc(o.get("ram","Not stated"))} GB</td><td>{esc(o.get("storage","Not stated"))} GB</td><td><b>${esc(o["price"])}</b><br><span class="small">{esc(o["price_label"])}</span></td><td>{esc(o.get("terms") or "Not stated; confirm at checkout.")}</td></tr>' for o in offers)
    page('/compare/',f'Compare VPS prices, RAM and terms | {month}',f'Compare {len(offers)} VPS plans by advertised USD price, resources and billing commitment in {month}.',template('compare.html',comparison_rows=comparison,empty='' if offers else empty,**common),[item_list(offers,domain)])
    source_rows=''.join(f'<li><h3><a href="/providers/{p["id"]}/">{esc(p["name"])}</a><span class="status-tag">{esc(attempts.get(p["id"],{}).get("status","not checked").replace("_"," "))}</span></h3><p>{esc(attempts.get(p["id"],{}).get("message","Not checked yet"))}</p><a href="{esc(p["source_url"])}" rel="noopener">Official source →</a></li>' for p in providers.values())
    source_content=f'''<article class="prose"><div class="eyebrow">METHODOLOGY &amp; SOURCE HEALTH</div><h1>Show the source.<br>Keep the conditions.</h1><p>We read publicly accessible provider pages using a named collector. We respect robots.txt, verify TLS, make bounded requests, and stop on access restrictions. We do not log in to providers or bypass bot checks.</p><h2>What “verified” means here</h2><p>A deterministic parser matched a named plan, its published price and supporting text. It is not an independent test of performance, uptime, stock, checkout eligibility or service quality. Provider-displayed percentages are labeled as their claims.</p><p>Each record includes the official URL, collection timestamp, captured offer text and a SHA-256 source fingerprint. No matching evidence means no published price. Trial credits are not subscription prices.</p><h2>Freshness and failures</h2><p>The schedule is {esc(config['policy']['cron'])} UTC (every six hours). A source failure removes that source's current prices on the next successful build. Builds exclude snapshots older than {config['policy']['max_age_hours']} hours and expired offers. If automation stops altogether, static pages cannot update themselves; the browser displays an overdue warning when JavaScript is enabled. Check the collection date and official source.</p><h2>Provider coverage</h2><ul class="source-list">{source_rows}</ul><h2>How to compare fairly</h2><p>Check the full billing commitment, renewal, taxes, region, IPv4, backup charges and management level. A monthly equivalent may require upfront payment. We do not convert currencies or calculate an unverified total contract cost.</p><h2>Open data and corrections</h2><p><a href="/data/offers.json">Download the current dataset</a> or <a href="{esc(config['site']['repository'])}/issues">report a correction on GitHub</a>. This independent directory is not affiliated with the listed providers.</p></article>'''
    page('/sources/',f'Sources and verification method | {brand}','Official source coverage, collection failures and the verification method behind VPS Deals.',source_content)
    affiliate=any(p['affiliate_url'] for p in providers.values())
    disclosure='Some provider links are affiliate links. If you purchase through a labeled link, we may earn a commission.' if affiliate else 'No affiliate tracking links are active in this snapshot. All provider links go directly to their official pages.'
    page('/disclosure/',f'Affiliate disclosure | {brand}','How provider links and future affiliate relationships are disclosed.',f'<article class="prose"><h1>Affiliate disclosure</h1><p>{disclosure}</p><p>When an approved program is enabled, links are marked as sponsored and the offer page displays a disclosure. Affiliate status does not change which evidence is required or the provider-name ordering.</p><h2>Editorial boundaries</h2><p>No paid rankings, fabricated coupons, invented reviews or unverified commission claims. We do not use cookie injection, brand bidding or self-referrals. Provider terms and final checkout pricing always control.</p><h2>Privacy</h2><p>This static site sets no advertising cookies and includes no third-party analytics. The hosting provider may process standard request logs under its own privacy policy. Provider websites have separate policies.</p></article>')
    page('/404/',f'Page not found | {brand}','This page is not available.','<article class="prose"><h1>This offer is no longer here.</h1><p>It may have expired or failed verification.</p><a href="/">Return to current offers</a></article>',index=False)
    (out/'404.html').write_text((out/'404/index.html').read_text(encoding='utf-8'),encoding='utf-8')
    shutil.copytree(ROOT/'assets',out/'assets')
    (out/'data').mkdir(); public_data={**data,'offers':offers}
    (out/'data/offers.json').write_text(json.dumps(public_data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (out/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{xml_escape(url)}</loc><lastmod>{xml_escape(date)}</lastmod></url>' for url,date in sitemap)+'</urlset>\n',encoding='utf-8')
    (out/'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {domain}/sitemap.xml\n',encoding='utf-8')
    (out/'_headers').write_text('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: DENY\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n  Content-Security-Policy: default-src \'self\'; script-src \'self\'; style-src \'self\'; img-src \'self\'; object-src \'none\'; base-uri \'none\'; frame-ancestors \'none\'\n  Cache-Control: public, max-age=300\n',encoding='utf-8')
    return {'offers':len(offers),'pages':len(list(out.rglob('*.html'))),'output':str(out)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--config');p.add_argument('--sync-workflow',action='store_true');args=p.parse_args()
    config=load_config(args.config)
    if args.sync_workflow:
        path=ROOT/'.github/workflows/update.yml';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(workflow_text(config),encoding='utf-8')
    data=json.loads((ROOT/'data/offers.json').read_text(encoding='utf-8'))
    print(json.dumps(build(config,data)))

if __name__=='__main__':main()
