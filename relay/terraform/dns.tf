data "cloudflare_zone" "this" {
  filter = {
    name = var.zone_name
  }
}

# Every house, in one record, forever.
#
# The relay routes by the SNI of each handshake and the certificate is proved over TLS, so DNS never
# has to learn a house's name: registering one writes nothing here. That is what keeps this zone
# static, and a zone that never changes at runtime is a zone this directory can own completely.
#
# The wildcard answers for names no house has claimed, which is fine and was checked: an unregistered
# SNI is refused at the relay with `unrecognized_name` and no certificate offered, so a name that
# resolves is not a house that answers.
#
# `proxied = false` is load-bearing, not a preference. Cloudflare's orange cloud terminates TLS at
# Cloudflare, which would put a cloud back between a person and their light switch and quietly undo
# the one property everything else rests on. docs/away.md says so under *Rules that do not change*.
resource "cloudflare_dns_record" "houses_v4" {
  zone_id = data.cloudflare_zone.this.zone_id
  name    = "*.${var.zone_name}"
  type    = "A"
  content = local.relay_ipv4
  ttl     = 300
  proxied = false
  comment = "Every house. Gray cloud on purpose: proxying would terminate TLS at Cloudflare."
}

resource "cloudflare_dns_record" "houses_v6" {
  count = local.make_box || var.relay_ipv6 != "" ? 1 : 0

  zone_id = data.cloudflare_zone.this.zone_id
  name    = "*.${var.zone_name}"
  type    = "AAAA"
  content = local.relay_ipv6
  ttl     = 300
  proxied = false
  comment = "Every house, over IPv6. Gray cloud for the same reason as the A record."
}

# Only Let's Encrypt may issue for anything under this domain. Each house asks for its own
# certificate over TLS-ALPN-01 through the relay, so this is the one place that can say, once and
# for the whole zone, that nobody else's certificate for a house's name would be valid.
resource "cloudflare_dns_record" "caa_issue" {
  zone_id = data.cloudflare_zone.this.zone_id
  name    = var.zone_name
  type    = "CAA"
  ttl     = 3600
  comment = "Houses get their certificates from Let's Encrypt and nowhere else."

  data = {
    flags = 0
    tag   = "issue"
    value = "letsencrypt.org"
  }
}

# And no wildcard certificate for anybody. A house proves one name, its own; nothing in this design
# ever needs a certificate covering every house at once, and a certificate that did would be the
# single worst thing that could leak. Drop this record if that ever stops being true.
resource "cloudflare_dns_record" "caa_no_wildcard" {
  zone_id = data.cloudflare_zone.this.zone_id
  name    = var.zone_name
  type    = "CAA"
  ttl     = 3600
  comment = "No wildcard certificate for this domain, ever."

  data = {
    flags = 0
    tag   = "issuewild"
    value = ";"
  }
}

# Without this the two records above say nothing. While Universal SSL is on, Cloudflare answers
# CAA queries with its own CAs added to ours -- issue and issuewild for DigiCert, Google, SSL.com,
# Comodo and Let's Encrypt -- so any of them could issue for a house's name, wildcards included.
# They never appear in the records API, only in what the zone serves; seen with dig on 1 October
# 2026. Universal SSL is the certificate Cloudflare shows for proxied records, and this zone has
# none: every record here is gray cloud on purpose, so turning it off costs nothing.
#
# Needs Zone > SSL and Certificates > Edit on the operator's token, beside DNS > Edit.
resource "cloudflare_universal_ssl_setting" "off" {
  zone_id = data.cloudflare_zone.this.zone_id
  enabled = false
}

# The address in the name, delegated once (docs/away.md, the alias that covers home). home.elyir.app
# belongs to the nameserver on the relay box, which answers 192-168-86-53.<house>.home.elyir.app with
# that LAN address for a carried house and nothing else. It is still one write, made here, forever:
# no house ever causes a DNS write -- the names are worked out from the question, not stored.
resource "cloudflare_dns_record" "ns1_v4" {
  zone_id = data.cloudflare_zone.this.zone_id
  name    = "ns1.${var.zone_name}"
  type    = "A"
  content = local.relay_ipv4
  ttl     = 300
  proxied = false
  comment = "The relay box, as the nameserver for home.${var.zone_name}."
}

resource "cloudflare_dns_record" "ns1_v6" {
  count = local.make_box || var.relay_ipv6 != "" ? 1 : 0

  zone_id = data.cloudflare_zone.this.zone_id
  name    = "ns1.${var.zone_name}"
  type    = "AAAA"
  content = local.relay_ipv6
  ttl     = 300
  proxied = false
  comment = "The relay box over IPv6, as the nameserver for home.${var.zone_name}."
}

resource "cloudflare_dns_record" "home_delegation" {
  zone_id = data.cloudflare_zone.this.zone_id
  name    = "home.${var.zone_name}"
  type    = "NS"
  content = "ns1.${var.zone_name}"
  ttl     = 3600
  comment = "Every house's name at home is answered by the relay box (relay/service/home.py)."
}
