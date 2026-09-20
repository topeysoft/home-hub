# The box.
#
# One small server whose entire job is to hold a TCP connection open per house and forward bytes it
# cannot read. It holds no certificate and no key for any house; the pass-through property was
# checked on 12 September 2026 and is a property of *not* configuring a plugin, so the one thing
# never to add to the config below is `plugin = "https2http"`. docs/away.md, piece 2.
#
# Bring your own box by setting `relay_ipv4`: nothing here is made, and the records in dns.tf point
# wherever you say. Running your own relay instead of the maker's is a supported path and always
# will be -- docs/service.md, *Rules that do not change*.

locals {
  make_box = var.relay_ipv4 == ""

  # What the records in dns.tf actually point at: the box made here, or the address you brought.
  relay_ipv4 = local.make_box ? one(hcloud_server.relay[*].ipv4_address) : var.relay_ipv4
  relay_ipv6 = local.make_box ? one(hcloud_server.relay[*].ipv6_address) : var.relay_ipv6
}

resource "hcloud_ssh_key" "admin" {
  count = local.make_box ? 1 : 0

  name       = "${var.relay_name}-admin"
  public_key = var.admin_ssh_public_key
}

# Two ports and nothing else. 443 is the whole service: frpc dials in on it and phones arrive on it,
# because frps detects the protocol and multiplexes both onto one port (checked against the frp
# documentation, 19 September 2026). That matters more than it sounds -- a hub that could only dial
# out on an odd port would fail in exactly the places away-from-home is for: hotels, offices and
# mobile networks.
#
# A port scan of this box should find a relay that offers nothing to an unrecognized name, and the
# ssh door. Narrow `admin_cidrs` to your own address if it is ever static.
resource "hcloud_firewall" "relay" {
  count = local.make_box ? 1 : 0

  name = "${var.relay_name}-firewall"

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "443"
    source_ips  = ["0.0.0.0/0", "::/0"]
    description = "Every house dials in here, and every phone away arrives here."
  }

  rule {
    direction   = "in"
    protocol    = "tcp"
    port        = "22"
    source_ips  = var.admin_cidrs
    description = "The operator. Key only: cloud-init turns password authentication off."
  }
}

resource "hcloud_server" "relay" {
  count = local.make_box ? 1 : 0

  name         = var.relay_name
  server_type  = var.relay_server_type
  location     = var.relay_location
  image        = var.relay_image
  ssh_keys     = [one(hcloud_ssh_key.admin[*].id)]
  firewall_ids = [one(hcloud_firewall.relay[*].id)]

  public_net {
    ipv4_enabled = true
    ipv6_enabled = true
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    frp_version = var.frp_version
    auth_token  = var.relay_auth_token
  })

  labels = {
    role = "relay"
  }

  lifecycle {
    precondition {
      condition     = var.admin_ssh_public_key != ""
      error_message = "admin_ssh_public_key is required to make a box: a relay you cannot log in to is a relay you cannot fix. Set relay_ipv4 instead if the box is already yours."
    }
    precondition {
      condition     = var.relay_auth_token != ""
      error_message = "relay_auth_token is required: without it any frpc on the internet could register a proxy on this relay. Generate one with `openssl rand -hex 32`."
    }
  }
}
