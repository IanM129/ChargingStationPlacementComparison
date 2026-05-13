from subprocess import call
import sumolib

netconvertBinary = sumolib.checkBinary('netconvert')


call([netconvertBinary, '-n', 'base.nod.xml', '-o', 'result.xml'])
