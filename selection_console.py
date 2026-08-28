import time

print("逆水寒大话骰连点器")
print()
print("请正好框选完整的游戏画面。")
print("不要包含窗口标题栏、窗口边框、黑边、桌面或其他窗口。")
print("完成框选后此窗口会自动关闭。")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
