variable "name" {
  type    = string
  default = "cost-guard"
}

variable "monthly_budget_usd" {
  type = number
}

variable "threshold_percent" {
  type    = number
  default = 100
}

variable "mode" {
  description = "dry_run only reports what would be paused. enforce actually pauses."
  type        = string
  default     = "dry_run"

  validation {
    condition     = contains(["dry_run", "enforce"], var.mode)
    error_message = "mode must be dry_run or enforce."
  }
}

variable "opt_in_tag" {
  type = object({
    key   = string
    value = string
  })
  default = {
    key   = "CostGuard"
    value = "enabled"
  }
}

variable "notification_emails" {
  type    = list(string)
  default = []
}