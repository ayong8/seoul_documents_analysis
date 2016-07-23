#!/usr/bin/env python
#-*- coding: utf-8 -*-
import os

end = 0
start = 14160
range_idx = 10

# node script를 통해 hwp파일을 txt파일로 변환한다
for i in range(1, 50000):
    end = start + range_idx
    print("End index is " + str(end))
    os.system("INDEX1=%d INDEX2=%d node ./node_hwp_test/test.js" % (start, end))
    start = end