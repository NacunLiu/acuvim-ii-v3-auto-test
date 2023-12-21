# File: kasaPlug.py
# Author: Hongjian Zhu
# Date: August 15, 2023
# Description: see below

"""
KasaSmartPlug Class

Create a Kasa Smart Plug object

Currently support plug power control (power on/off) and power cycle

ALL Changes to plug subject are using awaitable methods (Async), you must await :func:`update()` before sending commands

"""
import kasa
import asyncio
from ip_tracker import targetIp
import time

class KasaSmartPlug():
  
  def __init__(self,ip):
    self.Ip = ip
    self.dev = kasa.SmartPlug(ip)
  
  def loading_animation(self,duration, bar_length = 50, interval=0.1):
    total_ticks = int(duration / interval)
    for _ in range(total_ticks+1):
        # progress = int((_ / total_ticks) * bar_length)
        # bar = "[" + "=" * progress + " " * (bar_length - progress) + "]"
        # sys.stdout.write(f"\r{bar} {_ * 100 // total_ticks}%")
        # #sys.stdout.flush()
        time.sleep(interval)
    # sys.stdout.flush()
    # sys.stdout.write("\n")
    # sys.stdout.flush()
    return
    
  async def powerCycle(self,time=20):
    await self.dev.update()
    print('Power cycling the meter, please wait >>>>')
    await self.dev.turn_off()
    await asyncio.sleep(3)
    await self.dev.turn_on()
    self.loading_animation(time)
    #await asyncio.sleep(15)
    
  async def powerCycleNormal(self):
    await self.dev.update()
    print('Power cycling the meter, please wait >>>>')
    await self.dev.turn_off()
    #await asyncio.sleep(3)
    await asyncio.sleep(3)
    await self.dev.turn_on()
    #await asyncio.sleep(30)
    self.loading_animation(30)
    
  async def powerCycleSlow(self):
    await self.dev.update()
    print('Power cycling the meter, please wait >>>>')
    await self.dev.turn_off()
    await asyncio.sleep(2)
    await self.dev.turn_on()
    self.loading_animation(100)
    
  async def powerCycleSuperSlow(self):
    await self.dev.update()
    print('Store readings into FeRAM, please wait for 130 seconds >>>>')
    self.loading_animation(130)
    await self.dev.turn_off()
    await asyncio.sleep(3)
    await self.dev.turn_on()
    print('Powering up meter >>>>')
    self.loading_animation(40)
    

  async def powerCycleEnergy(self):
    await self.dev.update()
    print('Power cycling the meter, please wait >>>>')
    self.loading_animation(90)
    await self.dev.turn_off()
    await asyncio.sleep(2)
    await self.dev.turn_on()
    self.loading_animation(40)
    
  async def powerOff(self):
    await self.dev.update()
    print('Powering off the meter, please wait >>>>')
    await self.dev.turn_off()
    
  async def powerOn(self):
    await self.dev.update()
    print('Powering on the meter, please wait >>>>')
    await self.dev.turn_on()
    
  async def powerOnSlow(self):
    await self.dev.update()
    print('Powering on the meter, please wait >>>>')
    await self.dev.turn_on()
    self.loading_animation(70)
    
    
if __name__ == '__main__':
  PlugIp = targetIp
  for ip in PlugIp:
    plug = KasaSmartPlug(ip)
    asyncio.run(plug.powerCycle(2))

