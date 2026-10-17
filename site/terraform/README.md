# hub.elyir.com

Elyir Home Hub's site: the front page (`site/index.html`, design/site's D), `/install` and the waitlist. This folder
makes the things it runs on, once; `.github/workflows/site.yml` deploys the page on every change to `main`.

What it makes:

- the Pages project `elyir-home-hub`, served at `hub.elyir.com` (a proxied CNAME in the `elyir.com` zone);
- the D1 database `elyir-waitlist`, bound to the project as `WAITLIST`. It is the one Elyir waitlist, with the product
  a column, so Elyir Bench's site can bind it too. `functions/waitlist.js` makes its one table on first use.

To apply, with a token in the environment (Account > Cloudflare Pages > Edit, Account > D1 > Edit, Zone > DNS > Edit on
`elyir.com`):

```sh
export CLOUDFLARE_API_TOKEN=...
cd site/terraform
echo 'account_id = "..."' > terraform.tfvars     # ignored by git
terraform init && terraform plan && terraform apply
```

The state stays on the machine that applied it, as the relay's does. The deploy workflow needs its own, narrower
token: see the comment at the top of `.github/workflows/site.yml`.

Reading the list: `npx wrangler d1 execute elyir-waitlist --remote --command "SELECT product, count(*) FROM signups GROUP BY product"`.
