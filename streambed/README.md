# Streambed source code

Streambed needs Python 3.9+ to work. All dependencies are in the [requirements.txt](requirements.txt) file.

Files :

- [./charts/flink](./charts/flink/): Flink Helm chart using the Spotify Flink operator
- [./common_alloc.py](./common_alloc.py): monitoring statistics retrieval and CO implementation
- [./common_flink.py](./common_flink.py): Flink deployment methods and helper commands
- [./common_k8s.py](./common_k8s.py): Kubernetes, Kafka, and Prometheus methods
- [./common.py](./common.py): global variables and logging
- [./model.py](./model.py): partial RE implementation (missing parts are in notebooks such as the [RE estimation](../experiments/search_g5k_papermill.ipynb) or the [RE verification](../experiments/regression_g5k_papermill.ipynb))
- [./streambed.py](./streambed.py): interaction with Zeppelin, CE implementation, entry points, PromQL queries

The code will be deeply refactored and extended as some parts of the RE module are in notebooks. More details soon!