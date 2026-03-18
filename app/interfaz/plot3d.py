
import math
import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

def euler_to_rotmat(roll, pitch, yaw):
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    Rx = np.array([[1,0,0],[0,cr,-sr],[0,sr,cr]])
    Ry = np.array([[cp,0,sp],[0,1,0],[-sp,0,cp]])
    Rz = np.array([[cy,-sy,0],[sy,cy,0],[0,0,1]])
    return Rz @ Ry @ Rx

def make_cube(size=1.0):
    s = size / 2.0
    verts = np.array([
        [-s,-s,-s],[ s,-s,-s],[ s, s,-s],[-s, s,-s],
        [-s,-s, s],[ s,-s, s],[ s, s, s],[-s, s, s],
    ])
    faces = [[0,1,2,3],[4,5,6,7],[0,1,5,4],[2,3,7,6],[1,2,6,5],[0,3,7,4]]
    return (verts, faces)

class Plot3D:
    def __init__(self, figsize=(7.6,4.8), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi)
        self.ax = self.fig.add_subplot(111, projection="3d")
        self.ax.set_box_aspect([1,1,0.5])
        self.cube_poly = None
        self.scatter_path = None
        self.scatter_last = None
        self.reset_axes()

    def reset_axes(self):
        self.ax.cla()
        self.ax.set_xlabel("E (m)"); self.ax.set_ylabel("N (m)"); self.ax.set_zlabel("Alt (m)")
        self.ax.set_xlim(-5,5); self.ax.set_ylim(-5,5); self.ax.set_zlim(-1,5)
        self.ax.view_init(elev=25, azim=35); self.ax.grid(True)

    def draw_cube(self, verts_faces, translate=(0.0,0.0,0.0), color="#1f77b4", alpha=0.35, edgecolor="k"):
        verts, faces = verts_faces
        t = np.array(translate).reshape(1,3)
        vtx = verts + t
        poly3d = [[vtx[idx] for idx in face] for face in faces]
        if self.cube_poly is not None:
            self.cube_poly.remove()
        self.cube_poly = Poly3DCollection(poly3d, alpha=alpha, facecolor=color, edgecolor=edgecolor, linewidths=0.8)
        self.ax.add_collection3d(self.cube_poly)

    def update_scene(self, roll, pitch, yaw, pos_enu, base_cube):
        verts0, faces = base_cube
        R = euler_to_rotmat(roll, pitch, yaw)
        verts_rot = (R @ verts0.T).T + np.array(pos_enu).reshape(1,3)
        self.reset_axes()
        self.draw_cube((verts_rot, faces))

    def update_path(self, points):
        if points:
            P = np.array(points)
            if self.scatter_path is not None:
                self.scatter_path.remove()
            self.scatter_path = self.ax.scatter(P[:,0], P[:,1], P[:,2], s=4, alpha=0.7)
            if self.scatter_last is not None:
                self.scatter_last.remove()
            self.scatter_last = self.ax.scatter([P[-1,0]], [P[-1,1]], [P[-1,2]], s=30)

            minE, minN, minZ = np.min(P, axis=0)
            maxE, maxN, maxZ = np.max(P, axis=0)
            marginE = max(2.0, 0.15 * (maxE - minE + 1e-6))
            marginN = max(2.0, 0.15 * (maxN - minN + 1e-6))
            marginZ = max(1.0, 0.15 * (maxZ - minZ + 1e-6))
            self.ax.set_xlim(minE - marginE, maxE + marginE)
            self.ax.set_ylim(minN - marginN, maxN + marginN)
            self.ax.set_zlim(minZ - marginZ, maxZ + marginZ)
