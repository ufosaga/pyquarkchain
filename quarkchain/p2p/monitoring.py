import jsonrpcclient
import ipaddress
import argparse

import pprint
import json
from datetime import datetime

import asyncio
from jsonrpc_async import Server


"""
Given a node in P2P network, we'd like to be able to know what the entire network look like
and be able to query stats or adjust mining difficulty on demand
"""


def fetch_peers(ip, jrpc_port):
    json_rpc_url = "http://{}:{}".format(ip, jrpc_port)
    print("calling {}".format(json_rpc_url))
    peers = jsonrpcclient.request(json_rpc_url, "getPeers")
    return ["{}:{}".format(ipaddress.ip_address(int(p["ip"], 16)), int(p["port"], 16))
            for p in peers["peers"]]


def crawl_recursive(cache, ip, p2p_port, jrpc_port, ip_lookup={}):
    """
    given ip and p2p_port, jrpc_port, recursively crawl the p2p network
    assumes (jrpc_port-p2p_port) are the same across all peers
    looks up peer ip from ip_lookup, allowing this code to be run from outside network

    NOTE: run from within EC2 if you do not have ip_lookup
    """
    ip = ip_lookup[ip] if ip in ip_lookup else ip
    key = "{}:{}".format(ip, p2p_port)
    if key in cache:
        return
    cache[key] = fetch_peers(ip, jrpc_port)
    for peer in cache[key]:
        peer_ip, peer_p2p_port = peer.split(":")
        crawl_recursive(cache, peer_ip, int(peer_p2p_port), int(peer_p2p_port) + jrpc_port - p2p_port, ip_lookup)


def find_all_clusters(ip, p2p_port, jrpc_port, ip_lookup={}):
    """
    NOTE: returns json_rpc_port instead of p2p_port
    """
    cache = {}
    crawl_recursive(cache, ip, p2p_port, jrpc_port, ip_lookup)
    return ["{}:{}".format(c.split(":")[0], int(c.split(":")[1]) + jrpc_port - p2p_port) for c in cache.keys()]


def fetch_range(ip, jrpc_port_start, p2p_port_start, num):
    return {"{}:{}".format(ip, p2p_port_start + i): fetch_peers(ip, jrpc_port_start + i) for i in range(num)}


def json_topoplogy_d3(ip, p2p_port, jrpc_port, ip_lookup={}):
    cache = {}
    crawl_recursive(cache, ip, p2p_port, jrpc_port, ip_lookup)
    nodes = []
    ids = {}
    d3_id = 1
    for key, val in cache.items():
        nodes.append({
            "name": key,
            "label": "",
            "id": d3_id
        })
        ids[key] = d3_id
        d3_id += 1
    links = []
    for key, val in cache.items():
        for target in val:
            for x, y in ip_lookup.items():
                target = target.replace(x, y)
            links.append({
                "source": ids[key],
                "target": ids[target],
                "type": "PEER",
            })
    print(json.dumps({"nodes": nodes, "links": links}))


def print_all_clusters(ip, p2p_port, jrpc_port, ip_lookup={}):
    pprint.pprint(find_all_clusters(ip, p2p_port, jrpc_port, ip_lookup))


CONST_METRIC = "pendingTxCount"
CONST_INTERVAL = 1

async def async_stats(idx, server):
    response = await server.getStats()
    print("idx={};{}={}".format(idx, CONST_METRIC, response[CONST_METRIC]))


async def async_watch(clusters):
    servers = [(idx, Server("http://{}".format(cluster))) for idx, cluster in enumerate(clusters)]
    while True:
        await asyncio.gather(*[async_stats(idx, server) for (idx, server) in servers])
        print("... as of {}".format(datetime.now()))
        await asyncio.sleep(CONST_INTERVAL)


def watch_nodes_stats(ip, p2p_port, jrpc_port, ip_lookup={}):
    """
    :param ip:
    :param p2p_port:
    :param jrpc_port:
    :param ip_lookup:
    :return:
    keep printing CONST_METRIC from all clusters
    """
    clusters = find_all_clusters(ip, p2p_port, jrpc_port, ip_lookup)
    print("=======================IDX MAPPING=======================")
    pprint.pprint(["idx={};host:json={}".format(idx, cluster) for idx, cluster in enumerate(clusters)])
    asyncio.get_event_loop().run_until_complete(async_watch(clusters))


def main():
    parser = argparse.ArgumentParser()
    # do not use "localhost", use the private ip if you run this from EC2
    parser.add_argument(
        "--ip", default="54.186.3.84", type=str)
    parser.add_argument(
        "--jrpc_port", default=38491, type=int)
    parser.add_argument(
        "--p2p_port", default=38291, type=int)
    parser.add_argument(
        "--command", default="print_all_clusters", type=str)
    # eg: '{"172.31.15.196": "54.186.3.84"}'
    parser.add_argument(
        "--ip_lookup", default='{}', type=str)
    args = parser.parse_args()

    globals()[args.command](args.ip, args.p2p_port, args.jrpc_port, json.loads(args.ip_lookup))


if __name__ == "__main__":
    main()