terraform {
  required_version = ">= 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.25"
    }
  }
}

# The token comes from CLOUDFLARE_API_TOKEN in the environment: never a variable, never in state,
# never in this repository. It is the operator's token, scoped to this zone. No hub is ever given
# one -- Cloudflare scopes tokens to a zone and not to a record, so a token that let one house
# write its own name would let it write every other house's too. See docs/away.md, piece 3.
provider "cloudflare" {}
