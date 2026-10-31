# Real Terraform plan/apply, but it only manipulates local terraform_data state.
# Intentionally no GCP provider, credentials, network or cloud resources.
terraform {
  required_version = ">= 1.5.0, < 2.0.0"
}

variable "example_instance_size" {
  type    = string
  default = "medium"
}

resource "terraform_data" "staging_demo" {
  input = {
    environment = "staging"
    size        = var.example_instance_size
    owner       = "payment-service"
  }
}

output "demo_configuration" {
  value = terraform_data.staging_demo.output
}
