# ::ILANG
# ::MODULE{CONFIG|role:解析站点唯一配置真源}
# ::BOUNDARY{never:执行配置中的代码 隐藏厂商默认值}
"""Small documented I-Lang config subset; standard library only."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent

def slug(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')

def safe_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('Only public HTTPS URLs without credentials are allowed')
    return url

def load_config(path=None):
    text = Path(path or ROOT / '.ilang/site.ilang').read_text(encoding='utf-8')
    if text.splitlines()[0] != '::ILANG':
        raise ValueError('Missing ::ILANG header')
    cfg = {'providers': [], 'extractors': {}}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('::STATE{@SITE,'):
            cfg['site'] = json.loads('{' + line[len('::STATE{@SITE,'):-1] + '}')
        elif line.startswith('::POLICY{'):
            cfg['policy'] = json.loads(line[len('::POLICY'):])
        elif line.startswith('::EXTRACT{'):
            rule = json.loads(line[len('::EXTRACT'):])
            cfg['extractors'][rule['provider']] = rule
        elif line.startswith('::MODULE{'):
            section = line.split('{', 1)[1].split('|', 1)[0].rstrip('}')
        elif section == 'PROVIDERS' and line and not line.startswith(('#', '::', '[')):
            name, website, source, affiliate = (part.strip() for part in line.split('|'))
            cfg['providers'].append({'id': slug(name), 'name': name,
                'website': safe_url(website), 'source_url': safe_url(source),
                'affiliate_url': safe_url(affiliate) if affiliate else ''})
        elif section == 'FIELDS' and line and not line.startswith(('::', '#')):
            cfg['fields'] = line.split()
    for key in ('site', 'policy', 'fields'):
        if key not in cfg: raise ValueError('Missing config: ' + key)
    if cfg['site']['locale'] != 'en-US':
        raise ValueError('v1 supports en-US only; localize sources, currency and templates before adding a locale')
    ids = [p['id'] for p in cfg['providers']]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate provider IDs')
    safe_url(cfg['site']['domain'])
    if not 1 <= cfg['policy']['max_age_hours'] <= 168: raise ValueError('Invalid freshness limit')
    return cfg
