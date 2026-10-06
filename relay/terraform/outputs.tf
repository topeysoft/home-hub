output "zone_id" {
  description = "The zone every house's name lives in."
  value       = data.cloudflare_zone.this.zone_id
}

output "house_name_pattern" {
  description = "What a registered house is called, for the registration service to hand out."
  value       = "<house>.${var.zone_name}"
}

output "relay_ipv4" {
  description = "Where every house's name points: the box made here, or the one you brought."
  value       = local.relay_ipv4
}

output "relay_is_ours" {
  description = "Whether this directory rented the box, or was handed an address to point at."
  value       = local.make_box ? "made here" : "brought: ${var.relay_ipv4}"
}
