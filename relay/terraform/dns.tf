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
  count = var.relay_ipv4 == "" ? 0 : 1

  zone_id = data.cloudflare_zone.this.zone_id
  name    = "*.${var.zone_name}"
  type    = "A"
  content = var.relay_ipv4
  ttl     = 300
  proxied = false
  comment = "Every house. Grey cloud on purpose: proxying would terminate TLS at Cloudflare."
}

resource "cloudflare_dns_record" "houses_v6" {
  count = var.relay_ipv6 == "" ? 0 : 1

  zone_id = data.cloudflare_zone.this.zone_id
  name    = "*.${var.zone_name}"
  type    = "AAAA"
  content = var.relay_ipv6
  ttl     = 300
  proxied = false
  comment = "Every house, over IPv6. Grey cloud for the same reason as the A record."
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
