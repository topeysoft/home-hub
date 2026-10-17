data "cloudflare_zone" "site" {
  filter = {
    name = var.zone_name
  }
}

# One Elyir waitlist (5 October 2026), with the product a column. It lives here because the hub's page is the first
# to ask; Elyir Bench's site can bind the same database. The table is made by functions/waitlist.js on first use.
resource "cloudflare_d1_database" "waitlist" {
  account_id = var.account_id
  name       = "elyir-waitlist"
}

# A direct-upload project: no Git connection, no build here. What it serves is put together by site/build.sh and
# uploaded by .github/workflows/site.yml.
resource "cloudflare_pages_project" "site" {
  account_id        = var.account_id
  name              = var.project_name
  production_branch = "main"

  deployment_configs = {
    production = {
      d1_databases = {
        WAITLIST = { id = cloudflare_d1_database.waitlist.id }
      }
    }
  }
}

resource "cloudflare_pages_domain" "hub" {
  account_id   = var.account_id
  project_name = cloudflare_pages_project.site.name
  name         = "hub.${var.zone_name}"
}

resource "cloudflare_dns_record" "hub" {
  zone_id = data.cloudflare_zone.site.zone_id
  name    = "hub.${var.zone_name}"
  type    = "CNAME"
  content = cloudflare_pages_project.site.subdomain # the address Pages gave the project, not a guess
  ttl     = 1
  proxied = true
  comment = "Elyir Home Hub's site, served by Pages: the front page, /install and the waitlist."
}
