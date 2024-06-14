import os
from prometheus_api_client import PrometheusConnect
from prometheus_api_client.utils import parse_datetime
from datetime import datetime
from kubernetes import client as kubernetes_client, config, dynamic
import pandas as pd
import common
from io import StringIO
import yaml
import subprocess
import shlex
import datetime
from dateutil.tz import tzlocal
import pandas as pd
import logging
from time import sleep 

shell_log=False
logger = logging.getLogger('streambed')
env = os.environ

def run_command_async(command):
    if (isinstance(command, list) == False):
        commands = [command]
    else:
        commands=command
    processes = [None] * len(commands)
    for i in range(len(commands)):
        processes[i] = subprocess.Popen(shlex.split(commands[i]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return processes

def wait_for_command_async(processes):
    while processes:
        for i, process in enumerate(processes):
            output = process.stdout.readline().decode()
            if output == '' and process.poll() is not None:
                processes.remove(process)
                break
            if output:
                now=datetime.datetime.now(tzlocal())
                strnow = now.strftime("%Y-%m-%d %H:%M:%S")
                logger.debug("Log {0}: ".format(i) + output.strip())
    
    rc = process.poll()
    return rc    
def run_command(command, shell=True, log=True):
    logger.debug(command)
    if (isinstance(command, list) == False):
        commands = [command]
    else:
        commands=command
    processes = [None] * len(commands)
    for i in range(len(commands)):
        logger.debug(commands[i])
        processes[i] = subprocess.Popen(shlex.split(commands[i]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=shell, env=env)
    while processes:
        for i, process in enumerate(processes):
            output = process.stdout.readline().decode()
            if output == '' and process.poll() is not None:
                processes.remove(process)
                break
            if output and log:
                now=datetime.datetime.now(tzlocal())
                strnow = now.strftime("%Y-%m-%d %H:%M:%S")
                logger.debug("Log {0}: ".format(i) + output.strip())
    
    rc = process.poll()
    return rc
import os
def run_command_os(command):
    os.system(command)
    
class cd:
    """Context manager for changing the current working directory"""
    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)
def get_strnow():
    now=datetime.datetime.now(tzlocal())
    return now.strftime("%Y%m%d%H%M%S")
def wait_for_http_status(url, code, duration):
    import requests
    import time
    req_code = None
    start_time = time.time()
    end_time= time.time()
    while req_code != code and (end_time - start_time) < duration :
        try:
            time.sleep(1)
            r = requests.head(url)
            req_code = r.status_code
            logger.debug("\rWaiting status {} for {} seconds            ".format(code, end_time - start_time))
            return 0
        except requests.ConnectionError:
            logger.error("failed to connect to {} - {}".format(url, code))
            return 1
        end_time = time.time()    
       
def install_chart(path, name, params, timeout="120s"):
    with cd(path):
        param_str = ""
        for k in params.keys():
            param_str += "--set {}={} ".format(str(k).replace("!","."), str(params[k]).replace("!","."))
        command = "helm install {} . {} --namespace default --wait --timeout {} ".format(name, param_str, timeout)
        result = run_command(command, log = shell_log, shell=False)
        #result = run_command_os(command)
        return result    
    
def uninstall_chart(name, timeout="120s"):
    result = run_command("helm delete {}".format(name), log = shell_log, shell=False)
    return result

def get_label_nodes():

        # Configs can be set in Configuration class directly or using helper utility
    config.load_kube_config()
    api_instance = kubernetes_client.CoreV1Api()
    ip_address = common.ip_mode
    # Listing the cluster nodes
    node_list = api_instance.list_node()
    label_master = "node-role.kubernetes.io/controlplane"
    label_worker = "node-role.kubernetes.io/worker"
    count = 0
    manager_node = None
    jobmanager_node = None
    taskmanager_nodes = []
    for i, node in enumerate(node_list.items):
        logger.debug("%s\t%s" % (node.metadata.name, node.metadata.labels))
        address = [address.address for address in node.status.addresses if address.type=="InternalIP"][0]
        if ("tier" in node.metadata.labels and node.metadata.labels["tier"] == "manager" ):
            
            if ip_address:
                manager_node = address
            else:
                manager_node = node.metadata.name
            

        if ("tier" in node.metadata.labels and node.metadata.labels["tier"] == "jobmanager" ):
            if ip_address:
                jobmanager_node = address
            else:
                jobmanager_node = node.metadata.name

        if ("tier" in node.metadata.labels and node.metadata.labels["tier"] == "taskmanager" ):
            if ip_address:
                taskmanager_nodes = address
            else:            
                taskmanager_nodes.append(node.metadata.name)
    return (manager_node, jobmanager_node, taskmanager_nodes)


def delete_kafka_topic(name, namespace="kafka"):
    with kubernetes_client.ApiClient(k8s_configuration) as api_client:
        # Create an instance of the API class
        api_instance = kubernetes_client.CustomObjectsApi(api_client)
        
    try:
        api_instance.delete_namespaced_custom_object(
            group = "kafka.strimzi.io",
            version = "v1beta2",
            namespace = namespace,
            plural = "kafkatopics",
            name = name
        )
    except:
        logger.error("Error while removing {} (ns: {})".format(name, namespace))

def deploy_kafka(partitions, replicas, name="my-cluster", namespace="kafka", node_selector="kafka", antiaffinity=False, retention_duration=1440):
    if antiaffinity:
        kafka_yaml_template = """
        apiVersion: kafka.strimzi.io/v1beta2
        kind: Kafka
        metadata:
          name: {name}
          namespace: {namespace}
        spec:
          kafka:
            replicas: {replicas}
            listeners:
              - name: plain
                port: 9092
                type: internal
                tls: false
              - name: tls
                port: 9093
                type: internal
                tls: true
                authentication:
                  type: tls
              - name: external
                port: 9094
                type: nodeport
                tls: false
            storage:
              type: jbod # "Just a bunch of drives"
              volumes:
              - id: 0
                type: persistent-claim
                size: 100Gi
                class: local-path
                deleteClaim: true # change to false to keep the volume
            config:
              num.partitions: {partitions}
              offsets.topic.replication.factor: 1
              transaction.state.log.replication.factor: 1
              transaction.state.log.min.isr: 1
              default.replication.factor: 1
              min.insync.replicas: 1
              log.retention.minutes: {retention_duration}
            template:
              pod:
                affinity:
                  nodeAffinity:
                    requiredDuringSchedulingIgnoredDuringExecution:
                      nodeSelectorTerms:
                        - matchExpressions:
                          - key: tier
                            operator: In
                            values:
                            - {node_selector}      
                  podAntiAffinity:
                    requiredDuringSchedulingIgnoredDuringExecution:
                      - labelSelector:
                          matchExpressions:
                            - key: app.kubernetes.io/name
                              operator: In
                              values:
                                - kafka
                        topologyKey: "kubernetes.io/hostname"
          zookeeper:
            replicas: 1
            storage:
              type: persistent-claim
              size: 100Gi
              class: local-path
              deleteClaim: true 
            template:
              pod:
                affinity:
                  nodeAffinity:
                    requiredDuringSchedulingIgnoredDuringExecution:
                      nodeSelectorTerms:
                        - matchExpressions:
                          - key: tier
                            operator: In
                            values:
                            - {node_selector}      
          entityOperator:
            topicOperator: {{}}
            userOperator: {{}}
        """        
    else:
        kafka_yaml_template = """
        apiVersion: kafka.strimzi.io/v1beta2
        kind: Kafka
        metadata:
          name: {name}
          namespace: {namespace}
        spec:
          kafka:
            replicas: {replicas}
            listeners:
              - name: plain
                port: 9092
                type: internal
                tls: false
              - name: tls
                port: 9093
                type: internal
                tls: true
                authentication:
                  type: tls
              - name: external
                port: 9094
                type: nodeport
                tls: false
            storage:
              type: jbod # "Just a bunch of drives"
              volumes:
              - id: 0
                type: persistent-claim
                size: 100Gi
                class: local-path
                deleteClaim: true # change to false to keep the volume
            config:
              num.partitions: {partitions}
              offsets.topic.replication.factor: 1
              transaction.state.log.replication.factor: 1
              transaction.state.log.min.isr: 1
              default.replication.factor: 1
              min.insync.replicas: 1
              log.retention.minutes: {retention_duration}              
            template:
              pod:
                affinity:
                  nodeAffinity:
                    requiredDuringSchedulingIgnoredDuringExecution:
                      nodeSelectorTerms:
                        - matchExpressions:
                          - key: tier
                            operator: In
                            values:
                            - {node_selector}      
                  #podAntiAffinity:
                  #  requiredDuringSchedulingIgnoredDuringExecution:
                  #    - labelSelector:
                  #        matchExpressions:
                  #          - key: app.kubernetes.io/name
                  #            operator: In
                  #            values:
                  #              - kafka
                  #      topologyKey: "kubernetes.io/hostname"
          zookeeper:
            replicas: 1
            storage:
              type: persistent-claim
              size: 100Gi
              class: local-path
              deleteClaim: true 
            template:
              pod:
                affinity:
                  nodeAffinity:
                    requiredDuringSchedulingIgnoredDuringExecution:
                      nodeSelectorTerms:
                        - matchExpressions:
                          - key: tier
                            operator: In
                            values:
                            - {node_selector}      
          entityOperator:
            topicOperator: {{}}
            userOperator: {{}}
        """
    kafka_yaml = kafka_yaml_template.format(partitions=partitions, replicas=replicas, namespace=namespace, name=name, node_selector=node_selector, retention_duration=retention_duration)
    kafka_yaml = yaml.safe_load(StringIO(kafka_yaml))
    client = dynamic.DynamicClient(kubernetes_client.ApiClient(k8s_configuration))
    kafka_api = client.resources.get(
        api_version="kafka.strimzi.io/v1beta2", kind="Kafka"
    )

    kafka_api.create(body=kafka_yaml,namespace=namespace)

def create_kafka_topic(name, partitions, namespace="kafka"):
    kafka_topic_yaml_template = """
    apiVersion: kafka.strimzi.io/v1beta2
    kind: KafkaTopic
    metadata:
        labels:
            strimzi.io/cluster: my-cluster
        name: {topic_name}
        namespace: {namespace}
    spec:
        config: {{}}
        partitions: {partitions}
        replicas: 1
        topicName: {topic_name}
    """
    kafka_topic_yaml = kafka_topic_yaml_template.format(partitions=partitions, topic_name=name, namespace=namespace)
    kafka_yaml = yaml.safe_load(StringIO(kafka_topic_yaml))
    client = dynamic.DynamicClient(kubernetes_client.ApiClient(k8s_configuration))
    kafkatopic_api = client.resources.get(
        api_version="kafka.strimzi.io/v1beta2", kind="KafkaTopic"
    )

    kafkatopic_api.create(body=kafka_yaml,namespace="kafka")

def prom_connect(base_url=None):
    if base_url is None:
        base_url = common.prometheus_base_url
    prom = PrometheusConnect(url = base_url, disable_ssl=True )
    return prom

def prom_query_range(request, min_date, max_date, step="5s"):
    min_date_prom = datetime.datetime.fromtimestamp(min_date/1000)
    max_date_prom = datetime.datetime.fromtimestamp(max_date/1000)

    metric_data = common.prom.custom_query_range(
            request,
            start_time = min_date_prom,
            end_time = max_date_prom,
            step=step
        )
    ts = []
    val = []
    for metrics in metric_data:
        ts_list = [x[0] for x in metrics["values"]]
        val_list = [float(x[1]) for x in metrics["values"]]
        ts.extend(ts_list)
        val.extend(val_list)
    d =  {"ts":ts, "value":val} 
    df_metrics = pd.DataFrame.from_dict(d)
    df_metrics["dt"] = pd.to_datetime(df_metrics['ts'], unit="s") #debug
    df_metrics["second"] = df_metrics['ts'] - df_metrics['ts'].min()
    return df_metrics
def init_remote():
    g5k = False

    path_helm = "$HOME/tools/"
    global env
    env["PATH"] = os.environ.get("PATH") + ":" + os.environ.get("HOME") + "/tools"
    env["KUBECONFIG"] = os.environ.get("HOME") + "/.kube/config"
    # specific Grid5k : add $HOME/tools to PATH as PATH is not set in central Jupyter
    #new_path = os.environ.get("PATH") + ":" + os.environ.get("HOME") + "/tools"
    #kubeconfig = os.environ.get("HOME") + "/.kube/config"
    #env = dict(PATH=new_path, KUBECONFIG=kubeconfig)

    shell_log = True


    (manager_node, jobmanager_node, taskmanager_node) = get_label_nodes()

    # local
    #flink_base_url = "http://flink.127-0-0-1.sslip.io:30080"
    #zeppelin_base_url = "http://zeppelin.127-0-0-1.sslip.io:30080"
    #prometheus_base_url = "http://admin:prom-operator@prometheus.127-0-0-1.sslip.io:30080"
    #kafka_bridge_base_url = "http://kafka.127-0-0-1.sslip.io:30080"
    #dynamic_flink_url = False
    common.prom = prom_connect(common.prometheus_base_url)
    # init kube
    config.load_kube_config()
    global k8s_configuration    
    k8s_configuration = kubernetes_client.Configuration.get_default_copy()

def init_kind():
    path_helm = "$HOME/tools/"
    global env
    env["PATH"] = os.environ.get("PATH") + ":" + os.environ.get("HOME") + "/tools"
    env["KUBECONFIG"] = os.environ.get("HOME") + "/.kube/config"
    # specific Grid5k : add $HOME/tools to PATH as PATH is not set in central Jupyter
    #new_path = os.environ.get("PATH") + ":" + os.environ.get("HOME") + "/tools"
    #kubeconfig = os.environ.get("HOME") + "/.kube/config"
    #env = dict(PATH=new_path, KUBECONFIG=kubeconfig)

    shell_log = True


    (manager_node, jobmanager_node, taskmanager_node) = get_label_nodes()

    common.ip_mode = True      
    common.dynamic_flink_url = False

    common.flink_base_url = "http://flink.127-0-0-1.sslip.io"
    common.zeppelin_base_url = "http://zeppelin.127-0-0-1.sslip.io"
    common.prometheus_base_url = "http://admin:prom-operator@prometheus.127-0-0-1.sslip.io"
    common.kafka_bridge_base_url = "http://kafka.127-0-0-1.sslip.io"
    common.datagen_flink_base_url = "http://datagen-flink.127-0-0-1.sslip.io"
    #common.prometheus_base_url = "http://admin:prom-operator@{}:{}".format(manager_node, 30090)
    #common.zeppelin_base_url = "http://{}:{}".format(manager_node, 30088)
    #common.flink_base_url = "http://{}:{}".format(manager_node, 31600)
    #common.prometheus_base_url = "http://admin:prom-operator@{}:{}".format(manager_node, 30090)
    #common.kafka_bridge_base_url = "http://{}:{}".format(manager_node, 31080)
    common.prom = prom_connect(common.prometheus_base_url)

    # init kube
    config.load_kube_config()
    global k8s_configuration
    k8s_configuration = kubernetes_client.Configuration.get_default_copy()
  
def init_g5k():
    path_helm = "$HOME/tools/"
    global env
    env["PATH"] = os.environ.get("PATH") + ":" + os.environ.get("HOME") + "/tools"
    env["KUBECONFIG"] = os.environ.get("HOME") + "/.kube/config"
    # specific Grid5k : add $HOME/tools to PATH as PATH is not set in central Jupyter
    #new_path = os.environ.get("PATH") + ":" + os.environ.get("HOME") + "/tools"
    #kubeconfig = os.environ.get("HOME") + "/.kube/config"
    #env = dict(PATH=new_path, KUBECONFIG=kubeconfig)

    shell_log = True


    (manager_node, jobmanager_node, taskmanager_node) = get_label_nodes()
    
    common.ip_mode = False
    common.dynamic_flink_url = True
    common.zeppelin_base_url = "http://{}:{}".format(manager_node, 30088)
    common.flink_base_url = "http://{}:{}".format(manager_node, 31600)
    common.prometheus_base_url = "http://admin:prom-operator@{}:{}".format(manager_node, 30090)
    common.kafka_bridge_base_url = "http://{}:{}".format(manager_node, 31080)
    common.prom = prom_connect(common.prometheus_base_url)

    # init kube
    config.load_kube_config()
    global k8s_configuration
    k8s_configuration = kubernetes_client.Configuration.get_default_copy()
  
k8s_configuration = None