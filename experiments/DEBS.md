# Reproducing DEBS 24 experimentations

Every script has been launched on Grid5000, on the cluster [gros](https://www.grid5000.fr/w/Nancy:Hardware#gros) of the datacenter [nancy](https://www.grid5000.fr/w/Nancy:Hardware).

## Capacity estimator and configuration optimizer microbenchmarks 

The following scripts correspond to figure 9 and 10 in our paper. 

### CO/CE estimation scripts

The goal of these scripts is to execute the CO (and thus CE) module on a given configuration, for each query.

```bash
papermill estim_g5k_papermill.ipynb test_estim.ipynb -f scenarios/r1/g5k_q1.yaml
papermill estim_g5k_papermill.ipynb test_estim.ipynb -f scenarios/r1/g5k_q2.yaml
papermill estim_g5k_papermill.ipynb test_estim.ipynb -f scenarios/r1/g5k_q5.yaml
papermill estim_g5k_papermill.ipynb test_estim.ipynb -f scenarios/r1/g5k_q8.yaml
papermill estim_g5k_papermill.ipynb test_estim.ipynb -f scenarios/r1/g5k_q11.yaml
```

The obtained results are available in the [variable-results](./variable-results/) directory.

### CO/CE verification scripts

The goal of these scripts is to check the performance of the CO (and CE) using the given results.

```bash
papermill verif_g5k_papermill.ipynb test_verif.ipynb -f scenarios/r1/verif_g5k_q1.yaml
papermill verif_g5k_papermill.ipynb test_verif.ipynb -f scenarios/r1/verif_g5k_q2.yaml
papermill verif_g5k_papermill.ipynb test_verif.ipynb -f scenarios/r1/verif_g5k_q5.yaml
papermill verif_g5k_papermill.ipynb test_verif.ipynb -f scenarios/r1/verif_g5k_q8.yaml
papermill verif_g5k_papermill.ipynb test_verif.ipynb -f scenarios/r1/verif_g5k_q11.yaml
```
The obtained results are available in the [verification-results](./verification-results/) and [busyness-results](./busyness-results/) directories.

### Plot results

The scripts available in [plots/figure-9](plots/figure-9.ipynb) notebook and [plots/figure-10](plots/figure-10.ipynb) permit to plot respecively figure 9 (CE performance) and figure 10 (CO performance).

## Resource estimator

The following scripts correspond to table III (details on the obtained models), table IV (capacity planning results), and figure 11 in the paper (performance of large-scale runs using Streambed results).

### RE estimation scripts

These scripts launch the RE module and the consequent iterations of the CO and the CE modules.

```bash
papermill search_g5k_papermill.ipynb test_search-q1.ipynb -f scenarios/r5/g5k_q1-search.yaml
papermill search_g5k_papermill.ipynb test_search-q2.ipynb -f scenarios/r5/g5k_q2-search.yaml
papermill search_g5k_papermill.ipynb test_search-q5.ipynb -f scenarios/r5/g5k_q5-search.yaml
papermill search_g5k_papermill.ipynb test_search-q8.ipynb -f scenarios/r5/g5k_q8-search.yaml
papermill search_g5k_papermill.ipynb test_search-q11.ipynb -f scenarios/r5/g5k_q11-search.yaml
```

The [obtained values](./search-results/) are used to compute the values of the table III and IV, with additional details such as a plot of the RMSE and the RMSE ratio by search iteration ([plots/r6-score.pdf](plots/r6-score.pdf)), and the corresponding model for 4GB of memory per task slot ([plots/r6-model.pdf](plots/r6-model.pdf)). The notebook [final-r6-plots](final-r6-plots.ipynb) has been used to compute the model and generate the paper's figure. The obtained results are use the same computing method as in the regression script, described in the next section.

### RE verification scripts

These scripts deploy Apache Flink and Kafka on large scale scenarios. At least 110 nodes (counting we overprovisioned Apache Flink) have been booked on Grid'5000 to generate those.

```bash
papermill regression_g5k_papermill.ipynb final-r6-q1.ipynb -f scenarios/r6/g5k_q1.yml
papermill regression_g5k_papermill.ipynb final-r6-q2.ipynb -f scenarios/r6/g5k_q2.yml
papermill regression_g5k_papermill.ipynb final-r6-q5.ipynb -f scenarios/r6/g5k_q5.yml
papermill regression_g5k_papermill.ipynb final-r6-q8.ipynb -f scenarios/r6/g5k_q8.yml
papermill regression_g5k_papermill.ipynb final-r6-q11.ipynb -f scenarios/r6/g5k_q11.yml
```

The results are stored in the [./regression-results](./regression-results/) directory.
