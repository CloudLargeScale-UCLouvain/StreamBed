# Experiments

We assume the [infrastructure scripts](../infra) have been already launched, and a running Kubernetes cluster with all dependencies initialized is available.

## Nexmark benchmark

We test our approach using the Nexmark benchmark. Queries are executed using parametrizable [Apache Zeppelin notebooks](./zeppelin/).

## Notebooks

We provide the following notebooks to test the Resource Explorer (RE), Configuration Optimizer (CO), and Capacity Estimator (CE) modules :

- [RE estimation](./search_g5k_paparmill.ipynb)
- [RE analysis notebook](./final-r6-plots.ipynb)
- [RE verification](./regression_g5k_papermill.ipynb)
- [CO/CE estimation](./estim_g5k_papermill.ipynb)
- [CO/CE verification](./verif_g5k_papermill.ipynb)

All these scripts are based on the usage of [papermill](https://papermill.readthedocs.io/en/latest/) coupled to Jupyter notebooks, parameterized using YAML files.

For the usage of the RE estimation and CO/CE estimation notebooks, data should be initialized in Kafka. Our scripts use the Nexmark datagen for this purpose.

Each module is detailed with a configuration sample in the next sections. We will shortly merge and normalize the RE model scripts in the Streambed codebase.

### RE estimation script

This script is used to execute the RE module on the given configuration.

Sample configuration:

```yaml
xp_name: q11 # prefix
results_path: "search-results" # export directory

job_managers_qty: 2 # number of Flink job manager nodes
kafka_qty: 8 # number of Kafka nodes
kafka_partitions: 32 # number of Kafka partitions
kafka_replicas: 8 # number of Kafka replicas (pods)
kafka_node_selector: kafka # node selector for Kafka
# eval
events_num: 12000000000 # maximum total number of injected events
source_parallelism: 32 # number of sources
limit_backpressure_source: 250 # limit of backpressure at the source to consider the job failed

memory_granularity: 8192 # granularity considered
memory_range: # considered memory (only min/max used)
- 8192
- 16384
- 32768
- 65536
task_slots_minimal: 4 # minimum task slots 
task_slots_limits: 
- 80 # maximum task slots

optimization: # Bayesian optimization
  nb_iterations: 20 # max quantity of iterations
  base_estimator: gp # estimator
  n_initial_points: 6 # initial points
  initial_point_generator: grid 
  acq_func: EI # acquisition function
  random_state: 42 # seed used for the BO

reset_kafka_data: True # redeploy Kafka
previous_results: # usage of previous results (corners)
- "variable-results/r1/q11-final-20230423060007"
- "variable-results/r1/q11-final-20230424142915"

notebooks: ["/xp_intro_q11_kafka_custom_ratelimit"] # used notebook
cpu: 16 # quantity of cores by task manager
task_slots_per_task_manager: 16 # quantity of task slots by task manager
task_managers_qty: 8 # quantity of tasks managers
run: 0 # number of 
warmup: 300 # warmup duration
nb_runs_throughput: 1 # number 
nb_runs_parallelism: 1 # number of parallelism runs
g5k: True # g5k mode
dichotomic_mst_tuning: # tuning of CE
  initial_rate: 10000000000 # initial warmup
  slide_window: 75 # measurement duration
  size_window: 60 # injection duration
  observation_size: 30 # observation duration
  timeout: 600 # maximum duration of the CE run (without the last run)
  mean_threshold: 0.01 # ratio between incoming rate and actual processing rate: if below the iteration if successful
  higher_bound_ratio: 2 # ratio applied if there is no upper bound
  cooldown_throughput: 200 # source rate used during cooldown phase
  #warmup: 120 # usage of higher level parameter
  #nb_sources: usage of of higher level parameter

```

### RE verification notebook

This script's goal is to test the performance of the RE results on large-scale infrastructures.
It takes in input the output of the [RE estimation](./search_g5k_paparmill.ipynb) script.

An example of configuration is described below. We only describe the new values. The important parameters are especially the `target_rate` where the user set the very high rate he wants to check, and the `throughput_ratios` where the user indicates which percentages of the target rate will be tested for each configuration.

```yaml
results_estimation: ["search-results/q11-20230615031213"] # results of the search script
xp_name: "final-q11" # prefix of the result
g5k: True # g5k mode

model_type: linear # model type (linear/sqrt/log)

job_managers_qty: 1 
kafka_qty: 36
kafka_partitions: 144
kafka_replicas: 36
kafka_node_selector: kafka
reset_kafka_data: True

cpu: 16
task_slots_per_task_manager: 16

task_managers_qty: 16 # ignored
source_parallelism: 32 # ignored
source_capacity: 140000 # set sufficient for x1.5. This value corresponds at the same time of the capacity of a source, and of a Kafka partition in the current configuration.

memory_range: # considered memory values
- 8192
- 16384 
- 32768
- 65536

task_slots_limits: []
throughputs: 
- 20000000 # target rate. 

datagen_configuration:
  parallelism: 360 # parallelism used for the data generation
  cpu: 16
  memory : 65536
  task_managers_qty: 36
  task_slots: 16
  timeout: 600
  notebook: "/xp_datagen" # used notebook for data generation
  node_selector: "kafka"  

notebook: "/xp_intro_q11_kafka"
warmup: 300
ratio: 0.5 # minimal ratio between asked rate and obtained rate. The scripts stops if the actual ratio is lower.
timeout: 1800 # duration

throughput_ratios: # tested ratios of the target rate. For instance, the goal here is to test for 100%, 120% and 150% of the target rate for the same configuration.
- 1.5
- 1
- 1.2

ratio_overhead_throughput: 1.10 # overprovisioning factor. The default is 110%. 
```

### RE analysis notebook

The notebook [RE results](./final-r6-plots.ipynb) is used to evaluate the results of the RE estimation script. It computes the underlying model using the same subroutines as the previous scripts and also generates the paper figures.

### CE/CO estimation script

This script triggers an iteration of the CE and CO modules and is mainly used to evaluate the performance of both modules.

```yaml
xp_name: q1-final
results_path: "variable-results"

job_managers_qty: 4
kafka_qty: 16
kafka_partitions: 64
kafka_replicas: 16
kafka_node_selector: kafka
# eval
events_num: 12000000000 # estimate injection: 4M/sec in this config
source_parallelism: 64

memory_range: # tested memory values
- 8192
- 16384
- 32768
- 65536 
task_slots_limits: # tested task slot quantity values
- 67
- 70
- 75
- 80

reset_kafka_data: True # reset of Kafka installation and data

notebooks: ["/xp_intro_q1_kafka_custom_ratelimit"]
cpu: 16
task_slots_per_task_manager: 16
task_managers_qty: 8
run: 0
warmup: 120
nb_runs_throughput: 3
nb_runs_parallelism: 1
g5k: True
```

### CE/CO verification script

This script takes in input the output of the [CE/CO estimation script](./estim_g5k_papermill.ipynb) and uses it on the obtained rate to test the performance of these modules.

```yaml
results_estimation: "variable-results/r1/q1-final-20230421220421"
xp_name: "q1"
g5k: True

job_managers_qty: 2
kafka_qty: 0
kafka_partitions: 32
kafka_replicas: 8
kafka_node_selector: kafka
reset_kafka_data: False

task_managers_qty: 8
source_parallelism: 64

datagen_configuration: null # here, the datagen connector is used. The setting of the datagen_configuration value is used with Kafka.

notebook: "/xp_intro_q1_datagen"
warmup: 120
timeout: 600
sensitivity: 0.01
ratio: 1
```

## Results

The results are computed using the [final-r6-plots](./final-r6-plots.ipynb) notebook.

## Test with Kind

To launch the CO/CE estimation with Kind, please launch:

1. Execute the [Kind infrastructure notebook](../infra/kind/init-cluster.ipynb).

2. Execute the following command:

```bash
papermill estim_g5k_papermill.ipynb test_estim.ipynb -f ./scenarios/kind-estim.yml
```

You will need at least 16 GB of free memory.
