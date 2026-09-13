output "zone_id" {
  description = "The zone every house's name lives in."
  value       = data.cloudflare_zone.this.zone_id
}

output "house_name_pattern" {
  description = "What a registered house is called, for the registration service to hand out."
  value       = "<house>.${var.zone_name}"
}

output "relay_reachable" {
  description = "Whether the zone actually points anywhere yet."
  value       = var.relay_ipv4 == "" && var.relay_ipv6 == "" ? "no box yet: no records made" : "houses resolve to the relay"
}
