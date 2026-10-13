# 0.7b - the collector VM. Created only when var.create_vm is true (at S0).
#
# It gets its own VPC: the project's `default` network ships with rules that open
# port 22 (and RDP, ICMP) to the whole internet. Here the only inbound rule is
# SSH from Google's IAP range (spec §14.3).

locals {
  vm_count = var.create_vm ? 1 : 0
}

resource "google_compute_network" "collector" {
  count = local.vm_count

  name                    = "collector-net"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "collector" {
  count = local.vm_count

  name                     = "collector-${var.region}"
  network                  = google_compute_network.collector[0].id
  region                   = var.region
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

resource "google_compute_firewall" "iap_ssh" {
  count = local.vm_count

  name        = "allow-ssh-from-iap"
  network     = google_compute_network.collector[0].id
  direction   = "INGRESS"
  priority    = 1000
  description = "SSH only through Identity-Aware Proxy."

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["collector"]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}

# A separate disk that outlives the instance: the vnstock device id lives on it,
# so replacing the VM does not consume a new licence slot (D7).
resource "google_compute_disk" "collector_boot" {
  count = local.vm_count

  name   = "collector-prod-01-boot"
  zone   = var.zone
  type   = "pd-standard"
  size   = var.vm_disk_size_gb
  image  = "debian-cloud/debian-12"
  labels = merge(local.labels, { component = "collector" })

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [image]
  }
}

resource "google_compute_instance" "collector" {
  count = local.vm_count

  name         = "collector-prod-01"
  machine_type = "e2-micro"
  zone         = var.zone
  tags         = ["collector"]
  labels       = merge(local.labels, { component = "collector" })

  allow_stopping_for_update = true

  boot_disk {
    source      = google_compute_disk.collector_boot[0].id
    auto_delete = false
  }

  network_interface {
    subnetwork = google_compute_subnetwork.collector[0].id
    # Ephemeral public IP for outbound traffic to the feed; no inbound rule uses it.
    access_config {}
  }

  service_account {
    email  = google_service_account.this["sa-collector"].email
    scopes = ["cloud-platform"] # access is limited by IAM, not by scopes
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
  }
}
