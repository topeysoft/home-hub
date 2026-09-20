variable "zone_name" {
  description = "The domain every house is a subdomain of."
  type        = string
  default     = "elyir.app"
}

variable "relay_ipv4" {
  description = <<-EOT
    Bring your own box. Set this to an address that already runs frps and nothing is rented here:
    relay.tf makes no server and the records below point where you say. Leave it empty -- the
    default -- and the box in relay.tf is made and its address is used.

    Running your own relay instead of the maker's is a supported path and always will be.
    docs/service.md, *Rules that do not change*.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.relay_ipv4 == "" || can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}$", var.relay_ipv4))
    error_message = "relay_ipv4 must be a bare IPv4 address, or empty to make the box in relay.tf."
  }
}

variable "relay_ipv6" {
  description = "The address of your own box over IPv6, if it has one. Ignored when one is made here."
  type        = string
  default     = ""
}

variable "relay_name" {
  description = "What the box is called, to Hetzner and to whoever comes looking in a year."
  type        = string
  default     = "elyir-relay"
}

variable "relay_server_type" {
  description = <<-EOT
    The smallest thing that does this job. An idle house is one held-open TCP connection, so the
    constraint is bandwidth and not cores -- docs/service.md has the arithmetic. `cax11` is ARM,
    which frps is happy on, being a single Go binary.
  EOT
  type        = string
  default     = "cax11"
}

variable "relay_location" {
  description = <<-EOT
    Decided 19 September 2026: the EU, both because it is cheapest here and because the connection
    metadata this box necessarily holds is then held under the rules docs/service.md was written
    against. `fsn1` is Falkenstein; `hel1` is Helsinki and works identically.
  EOT
  type        = string
  default     = "fsn1"
}

variable "relay_image" {
  description = "Pinned rather than latest, so a rebuild a year from now is the same box."
  type        = string
  default     = "debian-12"
}

variable "frp_version" {
  description = <<-EOT
    Pinned to what was tested on 12 September 2026. The pass-through property is the whole point of
    this box, so the version that was checked is the version that runs. Moving it means checking it
    again -- docs/away.md, *What was verified*.
  EOT
  type        = string
  default     = "0.71.0"
}

variable "relay_auth_token" {
  description = <<-EOT
    What stops any frpc on the internet registering a proxy here. Generate with
    `openssl rand -hex 32`. This is the interim answer for one house: step 4 replaces it with the
    registration service asking, per house, whether there is an entitlement. docs/service.md.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}

variable "admin_ssh_public_key" {
  description = "The operator's public key. A relay you cannot log in to is a relay you cannot fix."
  type        = string
  default     = ""
}

variable "admin_cidrs" {
  description = <<-EOT
    Who may reach ssh. Narrow this to your own address if it is ever static; the default is open
    because a home address usually is not, and password authentication is off either way.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}
