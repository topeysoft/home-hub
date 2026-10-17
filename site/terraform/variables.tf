variable "account_id" {
  description = "The Cloudflare account the site and the list live in. Set TF_VAR_account_id, or terraform.tfvars."
  type        = string
}

variable "zone_name" {
  description = <<-EOT
    Where the hub's site is: hub.<zone_name> (design/site, D; the address follows Elyir Bench's U1). The company keeps
    the zone's apex, and Elyir Bench is bench.<zone_name>. Not elyir.app: names there are houses' own addresses.
  EOT
  type        = string
  default     = "elyir.com"
}

variable "project_name" {
  description = "The Pages project. Also its free address: <project_name>.pages.dev."
  type        = string
  default     = "elyir-home-hub"
}
