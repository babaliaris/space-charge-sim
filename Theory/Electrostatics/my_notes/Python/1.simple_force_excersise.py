import matplotlib.pyplot as plt

q = 1
a = 1.0

q1 = (0, a)
q2 = (0, 0)
q3 = (a, 0)
q4 = (a, a)

# Νέα σημεία προορισμού
p_upQ4       = (a, a + a/4)
p_rightQ4    = (a + a/4, a)
p_diagQ4     = (a - a / 4, a - a / 4)

fig, ax = plt.subplots()
ax.set_aspect('equal')

# Σχεδίαση φορτίων
points = [q1, q2, q3, q4]
labels = ['(0,a),q1=+q', '(0,0),q2=-2q', '(a,0),q3=+q', '(a,a),q4=+q']
for (x, y), label in zip(points, labels):
    ax.plot(x, y, 'o', color='black')
    ax.text(x + 0.05, y + 0.05, label, fontsize=10)

# Διανύσματα προς q4
dx_r = q2[0] - q4[0]
dy_r = q2[1] - q4[1]
ax.arrow(q4[0], q4[1], dx_r, dy_r, head_width=0.05, length_includes_head=True, color='red')

dx_g = q4[0] - q3[0]
dy_g = q4[1] - q3[1]
ax.arrow(q3[0], q3[1], dx_g, dy_g, head_width=0.05, length_includes_head=True, color='green')

dx_b = q4[0] - q1[0]
dy_b = q4[1] - q1[1]
ax.arrow(q1[0], q1[1], dx_b, dy_b, head_width=0.05, length_includes_head=True, color='blue')

# Νέα μαύρα διανύσματα από q4
for px, py in [p_upQ4, p_rightQ4, p_diagQ4]:
    dx = px - q4[0]
    dy = py - q4[1]
    ax.arrow(q4[0], q4[1], dx, dy, head_width=0.05, length_includes_head=True, color='purple')

# Ετικέτες στα μέσα των διανυσμάτων
red_mid_x = q4[0] + dx_r / 1.5
red_mid_y = q4[1] + dy_r / 2
ax.text(red_mid_x + 0.05, red_mid_y + 0.05, r'$\vec{r_{24}}$', color='red', fontsize=12)

green_mid_x = q4[0]
green_mid_y = q4[1] - dy_g / 2
ax.text(green_mid_x + 0.05, green_mid_y + 0.05, r'$\vec{r_{34}}$', color='green', fontsize=12)

blue_mid_x = q4[0] - dx_b / 1.5
blue_mid_y = q1[1]
ax.text(blue_mid_x - 0.1, blue_mid_y - 0.16, r'$\vec{r_{14}}$', color='blue', fontsize=12)



ax.text(p_upQ4[0] - 0.1, p_upQ4[1] + 0.01, r'$\vec{F_{34}}$', color='purple', fontsize=12)
ax.text(p_rightQ4[0] - 0.1, p_rightQ4[1] - 0.2, r'$\vec{F_{14}}$', color='purple', fontsize=12)
ax.text(p_diagQ4[0] - 0.16, p_diagQ4[1] + 0.08, r'$\vec{F_{24}}$', color='purple', fontsize=12)


# Διακεκομμένες γραμμές
ax.plot([q2[0], q1[0]], [q2[1], q1[1]], 'k--')  # από (0,0) στο (0,a)
ax.plot([q2[0], q3[0]], [q2[1], q3[1]], 'k--')  # από (0,0) στο (a,0)

ax.set_xlim(-0.5, a + 1.5)
ax.set_ylim(-0.5, a + 1.5)

ax.grid(True)

# Αφαίρεση αριθμών από τους άξονες
ax.set_xticks([])
ax.set_yticks([])

plt.xlabel('x')
plt.ylabel('y')

plt.show()
