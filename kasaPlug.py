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
    
  def loading_animation(self,duration):
    time.sleep(duration)
    return
    
  async def powerCycle(self,time=20):
    await self.dev.update()
    print('Power cycling plug {}, please wait >>>>'.format(self.Ip))
    await asyncio.sleep(2)
    await self.dev.turn_off()
    await asyncio.sleep(3)
    await self.dev.turn_on()
    self.loading_animation(time)
    
  async def powerCycleNormal(self):
    await self.dev.update()
    print('Power cycling the meter, please wait >>>>')
    await asyncio.sleep(2)
    await self.dev.turn_off()
    await asyncio.sleep(3)
    await self.dev.turn_on()
    #await asyncio.sleep(30)
    self.loading_animation(30)
    
  async def powerCycleSlow(self):
      await self.dev.update()
      print('Power cycling the meter, please wait >>>>')
      await asyncio.sleep(2)
      await self.dev.turn_off()
      await asyncio.sleep(2)
      await self.dev.turn_on()
      time.sleep(60)
    
  async def powerCycleSuperSlow(self):
    await self.dev.update()
    print('Store readings into FeRAM, please wait for 130 seconds >>>>')
    self.loading_animation(130)
    await self.dev.turn_off()
    await asyncio.sleep(3)
    await self.dev.turn_on()
    print('Powering up meter >>>>')
    self.loading_animation(50)
    

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

  async def powerOn(self,sleep = None):
    await self.dev.update()
    print('Powering on the meter, please wait >>>>')
    await self.dev.turn_on()
    if(sleep):
      time.sleep(30)
    
  async def powerOnSlow(self):
    await self.dev.update()
    print('Powering on the meter, please wait >>>>')
    await self.dev.turn_on()
    self.loading_animation(70)
    
    
if __name__ == '__main__':
  PlugIp = targetIp
  for ip in PlugIp:
    plug = KasaSmartPlug(targetIp[ip][1])
    asyncio.run(plug.powerCycle())


  # plug = KasaSmartPlug(PlugIp[0])
  # asyncio.run(plug.powerCycleSlow())


