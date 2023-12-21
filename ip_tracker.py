# File: ip_tracker.py
# Author: Hongjian Zhu
# Date: August 13, 2023
# Last Edit Date: Sept 18, 2023
# Description: see below
"""
This function will scan all Ips from router, return the target ip matched by Mac Address

Returns:
    Ip address (string)
"""
import subprocess
import re
from collections import defaultdict
NetDict = defaultdict(str)

target_mac1 = "78:8C:B5:B5:15:9C"
target_mac2 = "78:8C:B5:B5:07:58"
target_mac3 = "9C:A2:F4:95:3E:27"
target_mac4 = "9C:A2:F4:95:3D:55" #lab
ip_range1 = "172.27.27.80-120"
ip_range2 = "172.27.25.200-204"
ip_range = "172.27.26.1-80"

NetDict[target_mac1] = ip_range1
NetDict[target_mac2] = ip_range2
NetDict[target_mac3] = ip_range
NetDict[target_mac4] = ip_range


def get_ip_address(target_mac):
    try:
        output = subprocess.check_output(["arp", "-a"], universal_newlines=True)
        lines = output.splitlines()

        for line in lines:
            match = re.search(r"([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\s+([0-9A-Fa-f-]+)", line)
            if match:
                ip_address = match.group(1)
                mac_address = match.group(2).replace("-", ":").upper()
                if mac_address == target_mac:
                    return ip_address
        return None
    except subprocess.CalledProcessError:
        return None
    
# targetIp = get_ip_address(target_mac1) #Method abolished due to lack of consistency, target ip has to in the arp cache in order to be extracted

def nmap_scan(targetMAC):
    try:
        subprocess.check_output(["nmap", "-sn",NetDict[targetMAC],"-oN","scan_results.txt"], universal_newlines=True)
        return MacQuarry(targetMAC)
    except subprocess.CalledProcessError as e:
        print(e)
        return None
    
def MacQuarry(targetMAC):
    if(not targetMAC):
        print('Fail to load target MAC Address')
        return
    with open('scan_results.txt','r') as file:
        next(file)
        scan_output = file.read()
        
    # Regular expression patterns to match IP addresses and MAC addresses
    ip_pattern = r'(\d+\.\d+\.\d+\.\d+)'
    mac_pattern = r'[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}'
    #print(mac_pattern)
    ip_addresses = re.findall(ip_pattern, scan_output)
    mac_addresses = re.findall(mac_pattern, scan_output)

    # Create a dictionary to store IP-MAC pairs
    ip_mac_mapping = {}
    for ip, mac in zip(ip_addresses, mac_addresses):
        ip_mac_mapping[mac] = ip

    # Example: Match an IP address with its MAC address
    mac_to_match = targetMAC
    if mac_to_match in ip_mac_mapping:
        #print(f"MAC: {mac_to_match}, Ip: {ip_mac_mapping[mac_to_match]}")
        return ip_mac_mapping[mac_to_match]
    else:
        return None
    
#targetIp = get_ip_address(target_mac1) #Method abolished due to lack of consistency   
targetIp1 = nmap_scan(target_mac1)
targetIp2 = nmap_scan(target_mac2)
targetIp = [targetIp1, targetIp2]

if __name__ == '__main__':
    print(targetIp1,targetIp2)