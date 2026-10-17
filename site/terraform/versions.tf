terraform {
  required_version = ">= 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.25"
    }
  }
}

# The token comes from CLOUDFLARE_API_TOKEN in the environment: never a variable, never in state, never in this
# repository. It needs Account > Cloudflare Pages > Edit, Account > D1 > Edit and Zone > DNS > Edit on elyir.com.
provider "cloudflare" {}
