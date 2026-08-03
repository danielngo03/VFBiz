locals {
  database_network_name         = "vfbiz-ai-database-dev"
  database_subnetwork_name      = "vfbiz-ai-cloud-run-dev"
  database_instance_name        = "vfbiz-ai-postgres-dev"
  database_name                 = "vfbiz_ai"
  database_bootstrap_secret_id  = "vfbiz-ai-database-bootstrap-url-dev"
  database_submitter_secret_id  = "vfbiz-ai-document-submitter-db-url-dev"
  database_reconciler_secret_id = "vfbiz-ai-document-reconciler-db-url-dev"
  cloud_run_service_agent       = "service-${var.project_number}@serverless-robot-prod.iam.gserviceaccount.com"
  database_network_cidr         = "10.88.0.0/26"
  database_private_service_cidr = "10.89.0.0"
  database_private_service_bits = 24
}

resource "google_compute_network" "database" {
  count = var.database_foundation_enabled ? 1 : 0

  name                    = local.database_network_name
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "cloud_run_database" {
  count = var.database_foundation_enabled ? 1 : 0

  name                     = local.database_subnetwork_name
  region                   = var.region
  network                  = google_compute_network.database[0].id
  ip_cidr_range            = local.database_network_cidr
  private_ip_google_access = true
  stack_type               = "IPV4_ONLY"

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_compute_global_address" "database_private_service_access" {
  count = var.database_foundation_enabled ? 1 : 0

  name          = "vfbiz-ai-google-managed-services-dev"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = local.database_private_service_cidr
  prefix_length = local.database_private_service_bits
  network       = google_compute_network.database[0].id

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_service_networking_connection" "database" {
  count = var.database_foundation_enabled ? 1 : 0

  network                 = google_compute_network.database[0].id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.database_private_service_access[0].name]

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork_iam_member" "cloud_run_service_agent" {
  count = var.database_foundation_enabled ? 1 : 0

  project    = var.project_id
  region     = var.region
  subnetwork = google_compute_subnetwork.cloud_run_database[0].name
  role       = "roles/compute.networkUser"
  member     = "serviceAccount:${local.cloud_run_service_agent}"
}

resource "google_sql_database_instance" "ai" {
  count = var.database_foundation_enabled ? 1 : 0

  name                = local.database_instance_name
  region              = var.region
  database_version    = "POSTGRES_17"
  deletion_protection = true

  settings {
    tier                        = "db-f1-micro"
    edition                     = "ENTERPRISE"
    availability_type           = "ZONAL"
    activation_policy           = "ALWAYS"
    deletion_protection_enabled = true
    disk_type                   = "PD_SSD"
    disk_size                   = 20
    disk_autoresize             = false
    pricing_plan                = "PER_USE"
    user_labels                 = var.labels

    backup_configuration {
      enabled                        = true
      start_time                     = "20:00"
      location                       = var.region
      point_in_time_recovery_enabled = false

      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    insights_config {
      query_insights_enabled  = false
      record_client_address   = false
      record_application_tags = false
    }

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.database[0].id
      allocated_ip_range                            = google_compute_global_address.database_private_service_access[0].name
      enable_private_path_for_google_cloud_services = false
      ssl_mode                                      = "ENCRYPTED_ONLY"
    }

    maintenance_window {
      day          = 7
      hour         = 20
      update_track = "stable"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [
    google_project_service.required,
    google_service_networking_connection.database,
  ]
}

resource "google_sql_database" "ai" {
  count = var.database_foundation_enabled ? 1 : 0

  name     = local.database_name
  instance = google_sql_database_instance.ai[0].name

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "database_bootstrap_url" {
  count = var.database_foundation_enabled ? 1 : 0

  secret_id           = local.database_bootstrap_secret_id
  labels              = var.labels
  deletion_protection = true

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "database_submitter_url" {
  count = var.database_foundation_enabled ? 1 : 0

  secret_id           = local.database_submitter_secret_id
  labels              = var.labels
  deletion_protection = true

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_secret_manager_secret" "database_reconciler_url" {
  count = var.database_foundation_enabled ? 1 : 0

  secret_id           = local.database_reconciler_secret_id
  labels              = var.labels
  deletion_protection = true

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}
