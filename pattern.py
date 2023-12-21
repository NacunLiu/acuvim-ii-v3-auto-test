# File: pattern.py
# Author: Hongjian Zhu
# Date: August 13, 2023
# Description: see below
"""
Display test result
"""
import pyfiglet
from termcolor import colored
success = colored(pyfiglet.figlet_format("Test Completed"),'light_cyan')
fail = colored(pyfiglet.figlet_format("Test Failed"),'red',attrs=['bold'])
partialFail = colored(pyfiglet.figlet_format("Some Tests Failed"),'light_yellow',attrs=['bold'])
allPassed = colored(pyfiglet.figlet_format("ALL Tests Passed"),'light_green',attrs=['bold'])
# Create the PyFiglet text
text = pyfiglet.figlet_format("AcuTest GO", font="slant")

# Define a list of rainbow colors
rainbow_colors = ['light_grey','light_grey','cyan','cyan', 'blue','blue','light_blue','light_blue']

# Initialize an empty string to store the rainbow-colored text
starter = ''

# Iterate through each character in the text and apply a different color
for i, char in enumerate(text):
    # Use modulo to cycle through rainbow_colors
    color = rainbow_colors[i % len(rainbow_colors)]
    starter += colored(char, color)
    
if(__name__ == '__main__'):
    print(starter)
    print(fail)
    print(success)
    print(allPassed)
    print(partialFail)
