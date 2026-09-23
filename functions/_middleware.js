// Serve the Google Search Console ownership proof at its .html URL.
//
// Cloudflare Pages normalises /<name>.html to /<name> with a 308. Google follows
// that redirect and the property verified fine, but the acceptance rule for this
// site is "200 with no redirect", so this middleware short-circuits that single
// path and answers it directly. Every other request falls straight through to
// the static assets.
//
// The same string is also emitted as a real file at the site root by build.py
// (it copies google*.html from the repository root into the build output), so if
// Google ever issues a new proof file, update BOTH this constant and the file.
//
// Cloudflare requires this directory to sit at the root of the Pages project,
// not inside the build output directory ("site").

const PROOF_FILE = "google52388a0c5d659e3b.html";
const PROOF_PATH = `/${PROOF_FILE}`;

export async function onRequest(context) {
  try {
    if (new URL(context.request.url).pathname === PROOF_PATH) {
      return new Response(`google-site-verification: ${PROOF_FILE}`, {
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }
  } catch (err) {
    // Never let this middleware take the rest of the site down.
  }
  return context.next();
}
