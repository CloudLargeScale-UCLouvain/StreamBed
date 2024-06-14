# Infrastructure scripts

Infrastructure scripts to provision the Kubernetes cluster and deploy the needed modules for Streambed. We expect the user to have Jupyter installed to execute the scripts.

## Kind installation

> kind is a tool for running local Kubernetes clusters using Docker container “nodes”. kind was primarily designed for testing Kubernetes itself, but may be used for local development or CI. 

This mono-node installation is used for test purposes. It supposes having [Kind](https://kind.sigs.k8s.io/) - tested with version 0.11.1- installed. The test cluster can be parametrized in the [cluster.yaml](kind/cluster.yaml) file. 
Once everything is set up, the Jupyter notebook [./kind/init-cluster.ipynb](./kind/init-cluster.ipynb) should be launched. The installation takes dozens of minutes depending of the mood of the Docker Hub, and sufficient disk space should be available. Be patient!

## Grid5000 installation

> Grid'5000 is a large-scale and flexible testbed for experiment-driven research in all areas of computer science, with a focus on parallel and distributed computing including Cloud, HPC and Big Data and AI.

Grid'5000 provides access to a large amount of resources, mostly for academic users. We employ a [fork](https://github.com/guillaumerosinosky/terraform-grid5000-k8s-cluster.git) of the [Terraform Grid5000 K8S provisioner](https://github.com/pmorillon/terraform-grid5000-k8s-cluster) deploying a Rancher Kubernetes v1.22.adding logs and permitting to book in advance the nodes. The usage of this provider presupposes having a Grid5000 account, and everything set up on the control machine, please consult the [Grid5000 documentation](https://www.grid5000.fr/w/Getting_Started) for more details. Please note that it is possible to launch Streambed directly from one of the Grid5000 access machines, thus easying and speeding up the deployments. 

The choice of the target data center, cluster, and quantity of machines can be set in the [main.tf](g5k/main.tf). The right number of nodes should be set based on the rules described in the main [README.md](../README.md#additional-dependencies) (Kafka nodes + Flink nodes + manager + Kubernetes master).

Once everything is set up, either on the control node or on the Grid5000 access machine, the Jupyter notebook [./kind/init-cluster.ipynb](./kind/init-cluster.ipynb) should be launched. The provision and installation can take multiple dozens of minutes depending of the number of nodes and the mood of the mirror of the Docker Hub. Be patient!