output "site" {
  value = "https://hub.${var.zone_name}"
}

output "pages_address" {
  value = "https://${cloudflare_pages_project.site.subdomain}"
}
