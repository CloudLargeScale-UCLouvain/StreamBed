module "k8s_cluster" {
    source = "github.com/guillaumerosinosky/terraform-grid5000-k8s-cluster"
    nodes_count = 5 # number of nodes
    walltime = 1 # duration
    reservation = var.reservation # future reservation, if defined
    nodes_selector="{cluster='gros'}" # target cluster
    oar_job_name = "gepiciad_resource-estimator" # experimentation name
    kubernetes_version = "v1.22.4-rancher1-1"
    site = "nancy" # target datacenter
}