# Description: see below

"""
Extension Class for KasaPlug

ALL Changes to plug subject are using awaitable methods (Async), you must await :func:`update()` before sending commands

Add-on fe

"""
from kasaPlug import KasaSmartPlug
from ip_tracker import targetIp
import asyncio
class miniKasa(KasaSmartPlug):
    
    def __init__(self,Ip):
        super().__init__(Ip)
        
    async def recurring_switch(self):
        while(True):
            await self.powerCycle(50)
            
if __name__ == '__main__':
    PlugIp = targetIp
    for ip in PlugIp:
        KasaPlug = miniKasa(ip)
        asyncio.run(KasaPlug.recurring_switch())

    