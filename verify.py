# ::ILANG
# ::MODULE{VERIFY|role:检查站点链接 元数据 数据证据 和采集健康}
# ::BOUNDARY{never:把本地校验冒充Google富媒体测试或线上验证}
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree
from config import ROOT, load_config
from build import workflow_text

def verify(root=None):
    cfg=load_config(); root=Path(root or ROOT/'site'); problems=[]; count=0
    for path in root.rglob('*.html'):
        count+=1; text=path.read_text(encoding='utf-8')
        canonical=re.findall(r'<link rel="canonical" href="([^"]+)"',text)
        if len(canonical)!=1 or not canonical[0].startswith(cfg['site']['domain']):problems.append(f'{path}: canonical')
        for pattern in (r'<title>.+?</title>',r'name="description" content="[^"]+"',r'name="twitter:card"',r'property="og:image"'):
            if not re.search(pattern,text):problems.append(f'{path}: missing metadata {pattern}')
        for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>',text,re.S):
            try:json.loads(raw)
            except ValueError:problems.append(f'{path}: invalid JSON-LD')
        for link in re.findall(r'(?:href|src)="(/[^"#]*)"',text):
            target=root/link.lstrip('/')
            if link.endswith('/'):target=target/'index.html'
            if not target.is_file():problems.append(f'{path}: broken local link {link}')
    data=json.loads((root/'data/offers.json').read_text(encoding='utf-8'))
    for offer in data['offers']:
        for field in cfg['fields']:
            if field not in ('valid_until','price') and not offer.get(field):problems.append(f'{offer["id"]}: missing {field}')
        if 'price' in offer and not offer.get('evidence'):problems.append('Price without evidence')
    ElementTree.parse(root/'sitemap.xml')
    workflow=ROOT/'.github/workflows/update.yml'
    if not workflow.exists() or workflow.read_text(encoding='utf-8')!=workflow_text(cfg):problems.append('Workflow differs from I-Lang; run build.py --sync-workflow')
    if problems:raise ValueError('\n'.join(problems))
    return count,len(data['offers'])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--health',action='store_true');args=parser.parse_args()
    if args.health:
        data=json.loads((ROOT/'data/offers.json').read_text(encoding='utf-8'))
        failed=[s for s in data['sources'] if s['status']!='verified']
        for source in failed:print(f'::warning::{source["provider"]}: {source["status"]}')
        if not data['offers']:
            print('::error::No verified offers; truthful empty snapshot was published.');return 1
        return 0
    pages,offers=verify();print(f'PASS: {pages} pages; {offers} evidence-backed offers; links, JSON-LD, canonical, sitemap and schedule consistent.')
    return 0

if __name__=='__main__':sys.exit(main())
