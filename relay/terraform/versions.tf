terraform {
  required_version = ">= 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.25"
    }
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.51"
    }
  }
}

# The token comes from CLOUDFLARE_API_TOKEN in the environment: never a variable, never in state,
# never in this repository. It is the operator's token, scoped to this zone. No hub is ever given
# one -- Cloudflare scopes tokens to a zone and not to a record, so a token that let one house
# write its own name would let it write every other house's too. See docs/away.md, piece 3.
provider "cloudflare" {}

# Same rule as above: the token comes from HCLOUD_TOKEN in the environment. Hetzner was chosen on
# 19 September 2026 for one reason -- bandwidth is the only cost here that scales with use, and its
# included traffic is an order of magnitude cheaper than the alternatives. docs/service.md has the
# arithmetic. Nothing in this design depends on the provider; a box somewhere else only has to run
# frps and answer on 443.
provider "hcloud" {}
