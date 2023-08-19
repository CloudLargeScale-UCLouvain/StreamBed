#!/bin/bash

export PATH=$HOME/tools:$PATH # for grid5k

# give full rights to pod running in default (bad practice, but ok in our experimentation case)
kubectl apply -f ../common/cluster-role-binding-default.yaml

# ingress installed by kubespray
#kubectl apply -f ../common/nginx-controller.yaml

kubectl apply -f https://github.com/jetstack/cert-manager/releases/download/v1.5.3/cert-manager.yaml
kubectl --namespace cert-manager rollout status deployment/cert-manager-webhook
kubectl apply -f https://github.com/spotify/flink-on-k8s-operator/releases/download/v0.4.0-beta.8/flink-operator.yaml

# storage
kubectl create namespace manager

# local path provisioner installed by kubespray
#kubectl apply -f https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.21/deploy/local-path-storage.yaml
#kubectl apply -f ./cm-local-path.yaml # override default directory to /tmp (caution on reboot !)
kubectl apply -f ../common/pv-minio-local-path.yaml # default: uses nodes' local storage

sleep 30 # sleep for 30 seconds for application of configuration in local-path
helm repo add minio https://helm.min.io/
helm repo update
helm install minio minio/minio --namespace manager --version 8.0.10 -f ./values-minio.yaml

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install --namespace manager --version 30.0.2 prom prometheus-community/kube-prometheus-stack -f ./values-prom.yaml

kubectl apply -f ../common/pod-monitor.yaml

helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm upgrade --install loki grafana/loki-stack --namespace manager --version 2.6.0 -f ./values-loki.yaml

sleep 10 # sometimes timeout
# Kafka
kubectl create ns kafka
kubectl -n kafka apply -f ../common/strimzi-cluster-operator-0.28.0.yaml

# repo for kowl
helm repo add cloudhut https://raw.githubusercontent.com/cloudhut/charts/master/archives
helm repo update


kubectl apply -f ../common/zeppelin-configmap.yaml
kubectl apply -f ../common/zeppelin-pv.yaml
kubectl apply -f ../common/zeppelin-server.yaml

# ingress for minio, prom, grafana
kubectl apply -f ../common/ingress-localhost.yaml