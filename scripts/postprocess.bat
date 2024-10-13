@echo off

echo run opencc all to chs2
A:/EBookTools/OpenCC/bin/opencc.exe -i merge.csv -o merge.chs2.csv -c a2s2.json

echo run opencc all to chs
A:/EBookTools/OpenCC/bin/opencc.exe -i merge.csv -o merge.chs.csv -c a2s.json

echo filte chs by freq
python merge_csv.py  ./ filted.chs 8 merge.chs.csv

copy /Y filted.chs.txt  A:\ProjectPython

pause