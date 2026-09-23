# ::ILANG
# ::MODULE{TESTS|role:验证证据 提取 失效和配置驱动}
# ::BOUNDARY{never:将测试数据写入正式优惠数据}
import copy
import json
import shutil
import unittest
import uuid
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from config import ROOT,load_config
from scraper import extract,visible_text
from build import build,current_offers,offer_schema,workflow_text

@contextmanager
def writable_test_dir():
    """Use an ordinary directory because Windows sandbox ACLs can break tempfile."""
    path=ROOT/'work'/f'test-{uuid.uuid4().hex}'
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path,ignore_errors=True)

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config();self.now=datetime(2026,9,21,tzinfo=timezone.utc)
        (ROOT/'work').mkdir(exist_ok=True)
        self.p=self.cfg['providers'][0]
        self.sample='<html><script>fake price $0</script><p>67% off KVM 1 $ 19.49 $ 6.49 /mo Choose plan Renews at $11.99/mo for 2 years. Cancel anytime. 1 vCPU core 4 GB RAM 50 GB NVMe disk space</p></html>'
        self.offers=extract(self.p,self.cfg['extractors'][self.p['id']],self.sample,self.now.isoformat(),self.p['source_url'])
        self.data={'generated_at':self.now.isoformat(),'offers':self.offers,'sources':[]}
    def test_price_is_sale_price_not_original_or_renewal(self):
        self.assertEqual(self.offers[0]['price'],'6.49');self.assertEqual(self.offers[0]['renewal'],'11.99')
        self.assertNotIn('fake price',visible_text(self.sample))
    def test_missing_or_ambiguous_price_not_published(self):
        self.assertEqual(extract(self.p,self.cfg['extractors'][self.p['id']],self.sample.replace('6.49','contact us'),self.now.isoformat(),self.p['source_url']),[])
    def test_duplicate_mobile_desktop_cards_deduplicated(self):
        self.assertEqual(len(extract(self.p,self.cfg['extractors'][self.p['id']],self.sample*2,self.now.isoformat(),self.p['source_url'])),1)
    def test_ionos_term_and_price(self):
        p=self.cfg['providers'][1]
        records=extract(p,self.cfg['extractors'][p['id']],'<p>VPS S+ Save 17% $6 $ 2 /month for 3 months with a 1-year term 1 vCore CPU 2 GB RAM 60 GB NVMe</p>',self.now.isoformat(),p['source_url'])
        self.assertEqual(records[0]['price'],'2.00');self.assertEqual(records[0]['terms'],'for 3 months with a 1-year term')
    def test_expiry_and_stale_removed(self):
        self.data['offers'][0]['valid_until']='2026-09-20';self.assertEqual(current_offers(self.cfg,self.data,self.now),[])
        del self.data['offers'][0]['valid_until'];self.assertEqual(current_offers(self.cfg,self.data,self.now+timedelta(hours=37)),[])
    def test_no_invented_availability_expiry(self):
        schema=offer_schema(self.offers[0],self.p)
        self.assertNotIn('availability',schema);self.assertNotIn('priceValidUntil',schema)
    def test_config_edit_really_changes_built_provider(self):
        text=(ROOT/'.ilang/site.ilang').read_text(encoding='utf-8')
        with writable_test_dir() as temp:
            path=temp/'site.ilang'
            # Changing the provider row and ID in config changes the rendered page.
            path.write_text(text.replace('Hostinger |','Renamed Provider |'),encoding='utf-8')
            changed=load_config(path);out=temp/'rendered'
            build(changed,self.data,out,self.now)
            self.assertTrue((out/'providers/renamed-provider/index.html').exists())
            self.assertFalse((out/'providers/hostinger/index.html').exists())
            self.assertEqual(json.loads((out/'data/offers.json').read_text(encoding='utf-8'))['offers'],[])
    def test_changed_source_invalidates_old_offer(self):
        self.cfg['providers'][0]['source_url']='https://www.hostinger.com/changed'
        self.assertEqual(current_offers(self.cfg,self.data,self.now),[])
    def test_html_injection_escaped(self):
        self.data['offers'][0]['title']='<img src=x onerror=alert(1)>'
        with writable_test_dir() as temp:
            out=temp/'site';build(self.cfg,self.data,out,self.now)
            page=(out/'deals'/self.offers[0]['id']/'index.html').read_text(encoding='utf-8')
            self.assertNotIn('<img src=x',page);self.assertIn('&lt;img',page)
    def test_cron_from_ilang(self):
        self.cfg['policy']['cron']='21 */6 * * *'
        self.assertIn('21 */6 * * *',workflow_text(self.cfg))
    def test_missing_price_omitted(self):
        del self.data['offers'][0]['price'];self.assertEqual(current_offers(self.cfg,self.data,self.now),[])

if __name__=='__main__':unittest.main()
