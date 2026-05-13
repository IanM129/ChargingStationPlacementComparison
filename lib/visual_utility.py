def compare_lists(a : list, b : list):
    max_len = max(len(a), len(b))
    print("Compare lists (" + str(len(a)) + "|" + str(len(b)) + "):\n", end="")
    res = ""
    for i in range(max_len):
        val_a = a[i] if (len(a) > i) else None
        val_b = b[i] if (len(b) > i) else None
        res += f"  {i:5d}: {str(val_a):10s} | {str(val_b):10s}\n"
    print(res)
    return
def compare_dics(a : dict, b : dict):
    all_keys = a.keys() + b.keys()
    print(len(a.keys()),"|", str(len(b.keys())) + ":")
    for key in all_keys:
        val_a = a.get(key, None)
        val_b = b.get(keys, None)
        print(" ", key, ":", f"{str(val_a):10s} | {str(val_b):10s}")
    return
