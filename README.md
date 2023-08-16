# Streambed: capacity planning for steam processing

This repository contains instructions for reproducing the experiments in our ICDE'23 paper "Streambed: capacity planning for steam processing".

StreamBed is a capacity planning system for stream processing. It predicts, ahead of any production deployment, the resources that a query will require to process an incoming data rate sustainably, and the appropriate configuration of these resources. StreamBed builds a capacity planning model by piloting a series of runs of the target query in a small-scale, controlled testbed. We implement StreamBed for the popular Flink DSP engine. Our evaluation with large-scale queries of the Nexmark benchmark demonstrates that StreamBed can effectively and accurately predict capacity requirements for jobs spanning more than 1,000 cores using a testbed of only 48 cores.

## Table of Contents

- [Description & Requirements](#description--requirements)
- [Setup and Run Streambed](#install-and-run-streambed)
- [Experiments with StreamBed](#experiments-with-streambed)
- [StreamBed Source Code](#streambed-source-code)
- [Reproducing the ICDE23 results](#reproducing-the-icde23-results)
- [License](#license)

## Project Structure

Available directories:

- [infra](./infra): infrastructure setup
- [streambed](./streambed/): Streambed source code
- [experiments](./experiments/): Instructions on performing experiments with StreamBed and ICDE results
- [common](./common): shared scripts for notebooks

## Description & Requirements

**How to access**

Streambed can be downloaded from the following link: https://github.com/CloudLargeScale-UCLouvain/StreamBed

**Hardware dependencies**

Streambed assumes a working Kubernetes installation comprising an Apache Kafka installation (that can be deployed by Streambed scripts) and will iteratively deploy and test various Flink installations.

The Kubernetes cluster should be dimensioned accordingly. We assume that each Flink Job Manager, Task Manager and Kafka node has a dedicated node (a node can be bare-metal or a small VM):

- a Kafka installation of $K$ nodes preferably with fast SSDs (if deployed by Streambed)
- a Flink installation of 1 job manager and $T$ task managers
- a manager node whose goal is to contain transversal modules such as the monitoring stack
- the K8S master node
- the control computer where this repository has been cloned (usually a laptop or a gateway VM)

So for instance, a 4-node Kafka installation and a 4-node Flink installation, $K$ + $T$ + 1 + 1 + 1 = 11 nodes will be needed, added to the control node.

**Software dependencies**

A running Kubernetes cluster should be deployed on the nodes. We provide scripts for provision and installation for Kind and Grid5000, but Streambed can be used on any Kubernetes Cluster once the dependencies have been installed.

The control machine should have a running installation of [Jupyter](https://jupyter.org/), [papermill](https://papermill.readthedocs.io/en/latest/), and Python 3.9+. Additional Python dependencies are installed using pip automatically in the provided notebooks. The [cbc](https://github.com/coin-or/Cbc) solver is automatically installed by the [PuLP](https://coin-or.github.io/pulp/) Python library. If the infrastructure scripts are used, [Terraform v0.14.11](https://releases.hashicorp.com/terraform/0.14.11/) should be installed and a parameterized [Grid5000](https://www.grid5000.fr/w/Getting_Started) environment should be set, or [Kind](https://kind.sigs.k8s.io/) 0.11.1 should be installed. If not, the Kubernetes configuration file `.kube/config` should be set at its default place. The Kubernetes cluster (tested on Kubernetes v1.21 and v1.22) should have the following charts or operators installed:

- [Prometheus](https://artifacthub.io/packages/helm/prometheus-community/kube-prometheus-stack/30.0.2): famous monitoring framework
- [Apache Zeppelin](https://zeppelin.apache.org/docs/0.10.1/quickstart/install.html): notebooks for jobs or queries initialization and execution. We expect the jobs to be expressed as Zeppelin notebooks. Other methods can be easily implemented.
- [Spotify Flink-on-k8s operator](https://github.com/spotify/flink-on-k8s-operator/releases/tag/v0.4.2-beta.8): easy deployment of Apache Flink
- Working installation of [Nginx Ingress](https://github.com/kubernetes/ingress-nginx), used for Apache Flink, Apache Zeppelin, Apache Kafka
- Facultative helper modules:

  - [Local Path provisioner](https://github.com/rancher/local-path-provisioner/releases/tag/v0.0.21): storage solution if none is available, the [node path used for the storage](./infra/g5k/cm-local-path.yaml) should point to an SSD drive on the nodes, especially for Kafka deployment
  - [Strimzi Kafka operator](https://github.com/strimzi/strimzi-kafka-operator/releases/tag/0.28.0): easy deployment of Kafka, and topic management, if no existing Kafka installation is available.
  - Grafana (Prometheus UI)

## Install and Run StreamBed

### Install build-essentials (e.g., dependencies)

The installation of the Streambed Python dependencies is straightforward.

```bash
cd streambed
pip install -r requirements.txt
```

### Additional dependencies

Additional dependencies should be cloned, built and placed accordingly in the [./tmp](./tmp) directory before the deployment:

- [Rate-limited Kafka connector](https://github.com/guillaumerosinosky/flink-connector-kafka-ratelimit): this module permits Streambed to control the current reading rate. This connector is used in the job as a source. Our scripts expect the build `flink-sql-connector-kafka-ratelimit_2.12-1.14.2.jar` present in the [tmp](./tmp) directory.
- Facultative: [Nexmark benchmark](https://github.com/guillaumerosinosky/nexmark): [Nexmark](https://github.com/nexmark/nexmark) fork linked on Apache Flink 1.14.2. Our scripts expect the build `nexmark-flink-0.2-SNAPSHOT.jar` present in the [tmp](./tmp) directory.

We provide infrastructure deployment scripts in the [infra](./infra) directory for deployment on [Kind](https://kind.sigs.k8s.io/) and on the large-scale testbed [Grid5000](https://www.grid5000.fr/w/Grid5000:Home). Those permit the provisioning of the infrastructure, the installation of all the dependencies described above, and   Nexmark Zeppelin notebooks.

On an already available installation of Kubernetes, the usage of the [modules scripts](./infra/common/common_modules.sh) and [setup scripts](./infra/common/common_setup.sh) should be sufficient to deploy the dependencies.

:warning: **Caution:** These scripts expect the nodes to have nodes with the label `tier` set in the following way:

- `manager`: 1 (or more) node(s) for the deployment of Apache Zeppelin, Prometheus
- `jobmanager`: 1 node for Flink's job manager
- `kafka`: as many nodes as needed for the Kafka installation, if managed by Streambed. Kafka nodes can be colocated with the job manager if set in the configuration file.
- `taskmanager`: as many nodes as needed for Flink's task managers

### Ingresses

We provide ingresses for Apache Zeppelin, Kowl (Apache Kafka UI), Apache Flink, Prometheus, and Grafana. Those are parameterized to use the name `(module).127-0-0-1.sslip.io`, for instance [zeppelin.127-0-0-1.sslip.io](http://zeppelin.127-0-0-1.sslip.io). We then use port forwarding to forward the port of the manager node (80 by default with our deployment of [Ingress Nginx](./infra/common/nginx-controller.yaml)) directly on the control machine. These values can be parameterized in [infra/ingress-localhost.yaml](infra/ingress-localhost.yaml), and [streambed/charts/flink/values.yaml](streambed/charts/flink/values.yaml).

### Setup StreamBed

#### Zeppelin notebooks

Zeppelin execution notebooks should be prepared accordingly. The main goal of the Zeppelin notebooks is to:

- initialize the structure of the SQL tables in a customizable way
- set the parallelism to what is indicated by the CO module
- execute the target query

Moreover, the usage of Zeppelin notebooks permits changes on the fly on the queries, for development purposes.

[An example is provided for the Nexmark queries](./experiments/zeppelin/), but can be easily generalized to other queries or regular Flink jobs. More details in the Zeppelin [README](./experiments/zeppelin/).

#### Data initialization

Representative data should be initialized in Kafka: Streambed will directly read from Kafka the data, at various rates to estimate the MST rate (CE module), the parallelism of the tasks (CO module) and iteratively the model linking MST and configuration (RE module).

For the Nexmark benchmark, we provide an [initialization Zeppelin notebook](./experiments/zeppelin/xp_intro_init_kafka_2J1RECAWT.zpln).

#### Configuration

In the current state, the easier way to use Streambed is by using our experiments Jupyter notebooks, as described in the next section.
We will shortly merge and normalize Streambed, to permit usage without Jupyter notebooks.

## Experiments with StreamBed

Please see [here](./experiments) for a detailed description of performing experiments with StreamBed.

## StreamBed Source Code

Please see [here](./streambed) for a detailed description of the StreamBed source code.

## Reproducing the ICDE23 results

Please see [here](./experiments/ICDE.md) for a detailed description of the scripts used for the ICDE23 experiments.

## License

StreamBed is released under [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt)