#!/usr/bin/env python3
"""旧自动缺口采集池已暂停；不启动worker、不探测账号、不写presence。
历史实现恢复点a241b7e670460764af68e3e8e3e7d35ee9e32795。
"""
import sys


def main():
    print('已暂停：gap_pool 自动缺口采集池；未启动任何worker。', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
