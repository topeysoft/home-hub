# Mail to the maker, at addresses on this zone: security@, and whatever else is listed.
#
# Cloudflare's Email Routing receives for the zone and forwards each address to the people behind it.
# It only ever forwards: nothing is stored, and nothing is sent from the zone. The addresses are a map
# in terraform.tfvars -- `security = ["you@example.com"]` -- so adding one is a line and an apply, never
# a dashboard. The destinations are people's own mailboxes, which is why they live in tfvars beside the
# other things that are the operator's, and not in this repository.
#
# ONE STEP IS NOT TERRAFORM'S, by design. Cloudflare will not forward to a mailbox until that mailbox
# has said yes: the first apply sends each new destination a link, and mail to it is held back until
# somebody clicks it. That is the destination proving it wants the mail, which no API can do for it.
#
# Leave the map empty -- the default -- and nothing here is made: a relay run by somebody else needs no
# mail at all.

variable "email_forwards" {
  description = <<-EOT
    Addresses on the zone and where each forwards: { security = ["you@example.com"] } makes
    security@<zone_name> forward to that mailbox. The key is the part before the @; each value is one or
    more destinations. Empty, the default, turns mail off entirely.
  EOT
  type        = map(list(string))
  default     = {}

  validation {
    condition = alltrue([
      for local_part, to in var.email_forwards :
      can(regex("^[a-z0-9][a-z0-9._+-]*$", local_part)) && length(to) > 0 &&
      alltrue([for d in to : can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", d))])
    ])
    error_message = "Each key is the part before the @ (lowercase letters, digits, . _ + -), and each value one or more email addresses."
  }
}

variable "email_catch_all" {
  description = <<-EOT
    Where mail to any other address on the zone goes. Empty, the default, leaves Cloudflare's own
    catch-all alone, which drops it: an address nobody listed is an address nobody reads.
  EOT
  type        = list(string)
  default     = []
}

locals {
  email_on           = length(var.email_forwards) > 0
  email_destinations = toset(flatten(concat(values(var.email_forwards), [var.email_catch_all])))
}

# Routing on, and the MX and SPF records it needs at the apex. The wildcard in dns.tf is an A record
# for house names and does not meet these.
resource "cloudflare_email_routing_settings" "this" {
  count   = local.email_on ? 1 : 0
  zone_id = data.cloudflare_zone.this.id
}

resource "cloudflare_email_routing_dns" "this" {
  count   = local.email_on ? 1 : 0
  zone_id = data.cloudflare_zone.this.id

  depends_on = [cloudflare_email_routing_settings.this]
}

# Each mailbox mail may go to. An account-level object: one verification covers every zone.
resource "cloudflare_email_routing_address" "to" {
  for_each   = local.email_on ? local.email_destinations : toset([])
  account_id = data.cloudflare_zone.this.account.id
  email      = each.value
}

resource "cloudflare_email_routing_rule" "forward" {
  for_each = var.email_forwards
  zone_id  = data.cloudflare_zone.this.id
  name     = "${each.key}@${var.zone_name}"
  enabled  = true

  matchers = [{
    type  = "literal"
    field = "to"
    value = "${each.key}@${var.zone_name}"
  }]
  actions = [{
    type  = "forward"
    value = each.value
  }]

  depends_on = [cloudflare_email_routing_settings.this, cloudflare_email_routing_address.to]
}

resource "cloudflare_email_routing_catch_all" "this" {
  count   = local.email_on && length(var.email_catch_all) > 0 ? 1 : 0
  zone_id = data.cloudflare_zone.this.id
  name    = "everything else on ${var.zone_name}"
  enabled = true

  matchers = [{ type = "all" }]
  actions = [{
    type  = "forward"
    value = var.email_catch_all
  }]

  depends_on = [cloudflare_email_routing_settings.this, cloudflare_email_routing_address.to]
}

output "email_addresses" {
  description = "The addresses on the zone that forward somewhere, and where."
  value       = { for local_part, to in var.email_forwards : "${local_part}@${var.zone_name}" => to }
}
