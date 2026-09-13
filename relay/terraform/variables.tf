variable "zone_name" {
  description = "The domain every house is a subdomain of."
  type        = string
  default     = "elyir.app"
}

variable "relay_ipv4" {
  description = <<-EOT
    The relay's address. Every house's name points here and the relay sorts them out by SNI.
    Empty until the box exists: a plan against an empty value makes no records rather than failing,
    so this directory is reviewable before anything is rented.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.relay_ipv4 == "" || can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.relay_ipv4))
    error_message = "relay_ipv4 must be a bare IPv4 address, or empty while there is no box yet."
  }
}

variable "relay_ipv6" {
  description = "The relay's IPv6 address, if it has one. Same rules as relay_ipv4."
  type        = string
  default     = ""
}
