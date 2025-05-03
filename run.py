# run.py

import threading
from feature.ticket_timeout_pm import ticket_timeout_pm
from feature.ticket_timeout_od import ticket_timeout_od


def pm():
    ticket_timeout_pm()
    
def od():
    ticket_timeout_od()


if __name__ == '__main__':
    t1 = thrading.Thread(target=pm, daemon=True)
    t2 = thrading.Thread(target=od, daemon=True)
    
    t1.start
    t2.start
    t1.join()
    t2.join()