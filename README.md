# VPS Deals

Official VPS prices, clear terms, traceable sources. An independent English-language VPS offer directory built with Python's standard library and static HTML.

**Deployment status:** live and verified at [vpsdealradar.com](https://vpsdealradar.com/). Cloudflare Pages builds `main` with `python build.py` and publishes `site/`.

## Defaults used

- Brand: VPS Deals; repository: `vps-deals-promo-radar`.
- Niche: VPS hosting; locale: en-US; currency: USD.
- Seed sources: Hostinger, IONOS, OVHcloud, Hetzner, Vultr, DigitalOcean, Akamai Linode.
- No affiliate links, commission figures, income claims or social accounts have been invented.
- Official price pages are used where no dependable dedicated promotion feed is available. Ordinary prices are labeled separately from promotions.

## Run

Python 3.12 or later, no pip installation, no API keys and no inference service:

```sh
python scraper.py
python build.py --sync-workflow
python -m unittest discover -s tests -v
python verify.py
python -m http.server 8080 --directory site
```

The collector and generator both read `.ilang/site.ilang`. Provider names, URLs, affiliate destinations, parser patterns, locale, domain, freshness and schedule all come from that file. Change a provider row and rebuild: the provider page changes and prices for a removed or changed source disappear. This behavior is covered by a test that edits an actual temporary I-Lang file and renders a site.

## Data truth contract

- Each price has an official URL, fetch time, captured matching text and source SHA-256.
- HTML is parsed without executing scripts. Provider-specific, named-capture patterns must match the plan and its price together. A page with no safe match produces no offer.
- Requests respect robots.txt, crawl delays, public-host boundaries, TLS verification, timeouts, byte limits and access restrictions. The collector does not bypass 403/429, challenges or login.
- A source failure removes its prices from the new snapshot. The source-health page reports failures. No previous price gets a new verification timestamp.
- Missing dates and availability are omitted, not invented. The builder excludes expired offers and snapshots older than the configured 36 hours.
- Static HTML cannot remove itself if all scheduled jobs stop. The UI shows an overdue warning when JavaScript is available; timestamps remain visible without it. Maintenance is still necessary.
- Advertised monthly equivalents are not necessarily monthly billing. Terms and renewal conditions are shown. No unverified total-cost calculation or “best deal” ranking.

## Cloudflare Pages deployment

1. Create a public GitHub repository with this source tree on `main`.
2. In Cloudflare, use **Workers & Pages → Create → Pages → Connect to Git**. Authorize access only to this repository.
3. Project name: `vps-deals-promo-radar` if available; framework preset: None; build command: `python build.py`; output: `site`; production branch: `main`.
4. Set build variable `PYTHON_VERSION=3.12`. No deployment API token is needed with the Git integration.
5. If Cloudflare assigns a different hostname, edit `domain` in `.ilang/site.ilang` to that actual HTTPS hostname, rebuild and commit. Never leave canonical or sitemap URLs pointing to a guessed host.
6. Run the GitHub workflow once, confirm its data commit triggers a second successful Cloudflare deployment, then open the production URL and a detail page.
7. Test a live detail URL in [Google Rich Results Test](https://search.google.com/test/rich-results). Local `verify.py` checks JSON syntax and truth contracts, not Google's eligibility. VPS is modeled as a `Service` with `Offer`, so Google may report no supported product rich result. Do not mislabel the service or invent ratings to silence this.

See `DEPLOYMENT.md` for the remaining handoff checks. Generated output includes sitemap, robots, per-page canonical, Open Graph, Twitter card, ItemList, BreadcrumbList and Service/Offer/AggregateOffer markup. No FAQ is fabricated. Only one language ships, so hreflang is not needed yet.

## Update pipeline and cost

The generated `.github/workflows/update.yml` runs every six hours at minute 17 UTC, supports manual dispatch, tests, collects, builds, verifies and commits `data/offers.json` plus `site/`. Cloudflare Git integration publishes the data commit. No workflow is triggered by its own generated output paths. The built-in ephemeral `GITHUB_TOKEN` is used for GitHub writes; “no keys” means no user-supplied API keys, not absence of authentication.

Public repositories can use [standard GitHub-hosted runners for free](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job). Larger runners and excess storage are not covered by that claim. [Cloudflare Pages Free has 500 builds/month](https://developers.cloudflare.com/pages/platform/limits/); four updates/day is about 120–124 builds/month before additional pushes and retries. No paid resources are required by this implementation, but quotas and plan terms can change.

[Scheduled Actions can be delayed or dropped, and public-repository schedules can be disabled after 60 days without activity](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows). Source layouts, access rules and free plans can change. This is a low-maintenance pipeline, not a perpetual-motion guarantee. Enable GitHub workflow-failure notifications and occasionally check source coverage. A successful partial refresh emits warnings for unavailable sources; a zero-offer refresh publishes an honest empty page and then fails the health check.

## Monetization, once approved

Until a legitimate program approves the owner and provides a tracking link, outbound links remain official direct links. After approval, add only that destination to the provider's final I-Lang column. The generator automatically adds `rel="sponsored noopener"` and disclosure. Verify the actual regional program terms, eligibility, payout basis and permitted promotion methods before using it. No recurring commission is assumed.

`MONETIZATION.md` describes the staged plan. X and Facebook are deferred for v1. No automated social publishing or fake amplification is configured. Transferable value comes from useful content, maintained infrastructure and verifiable traffic/revenue records; no sale valuation is promised.

## Search and domain ownership

Registering a domain is optional and is a paid owner decision. A custom domain improves brand control and portability across hosts; age alone does not guarantee ranking. A pages.dev subdomain is not a transferable domain registration. Git commits and README links do not prove search authority. Useful original comparisons, reliable facts and earned links matter; structured data never guarantees a rich result.

If a domain is added, configure it in Pages first, change the I-Lang `domain`, rebuild all canonical/sitemap URLs and configure a permanent redirect from the old hostname. For future locales, use language directories, independently verified regional offers and reciprocal hreflang plus x-default. Do not simply relabel English data.

## I-Lang dialect

This project implements a small text configuration dialect, not a third-party runtime. `::STATE{@SITE, ...}` contains JSON key/value pairs after the entity marker. `::POLICY{...}` and `::EXTRACT{...}` contain JSON objects. `PROVIDERS` uses four pipe-separated columns; `FIELDS` is whitespace-separated. `RULE` and `BOUNDARY` describe constraints enforced by Python and tests. Unknown executable directives are never evaluated. Configuration is version-controlled and must be treated as trusted maintainer input, never populated from remote page instructions.

站点规则用 I-Lang 协议描述，见 .ilang/site.ilang；协议说明 ilang.ai。

