"""Read and patch a D88 floppy image (FM Towns 2HD), with FAT12 file lookup.

The D88 stores per-track sector blocks: a 688-byte disk header (with a 164-entry u32
track-offset table at 0x20), then for each track a run of sectors, each = a 16-byte
sector header (C,H,R,N, count u16, density, deleted, status, 5 reserved, datasize u16)
followed by `datasize` bytes of data.

We build a *flat image* = every sector's data concatenated in (track-index, R) order,
which is the linear order the FAT12 filesystem expects. We also remember, for each flat
sector, where its data lives inside the raw D88 so edits can be written back length-
preservingly.
"""
import struct

SECTOR_N_BYTES = {0: 128, 1: 256, 2: 512, 3: 1024}


def _as_bytes(src):
    if hasattr(src, "read"):
        return src.read()
    if isinstance(src, (bytes, bytearray)):
        return bytes(src)
    with open(src, "rb") as f:
        return f.read()


class D88:
    def __init__(self, image):
        self.image = bytes(image)
        # sectors: list of (flat_start, d88_data_offset, size) in linear FS order
        self.sectors = []
        self._parse()

    def _parse(self):
        d = self.image
        track_offsets = [
            struct.unpack("<I", d[0x20 + i * 4:0x24 + i * 4])[0] for i in range(164)
        ]
        flat = bytearray()
        for off in track_offsets:
            if off == 0:
                continue
            track = []
            p = off
            count = struct.unpack("<H", d[p + 4:p + 6])[0] if p + 6 <= len(d) else 0
            for _ in range(count):
                if p + 16 > len(d):
                    break
                r = d[p + 2]
                dsize = struct.unpack("<H", d[p + 14:p + 16])[0]
                data_off = p + 16
                track.append((r, data_off, dsize))
                p = data_off + dsize
            for r, data_off, dsize in sorted(track, key=lambda s: s[0]):
                self.sectors.append((len(flat), data_off, dsize))
                flat += d[data_off:data_off + dsize]
        self.flat = bytes(flat)

    # --- FAT12 ---
    def _bpb(self):
        f = self.flat
        return {
            "bps": struct.unpack("<H", f[11:13])[0],
            "spc": f[13],
            "reserved": struct.unpack("<H", f[14:16])[0],
            "nfat": f[16],
            "rootent": struct.unpack("<H", f[17:19])[0],
            "spf": struct.unpack("<H", f[22:24])[0],
        }

    def _fat12_next(self, fat, n):
        off = n + n // 2
        v = fat[off] | (fat[off + 1] << 8)
        return (v >> 4) if (n & 1) else (v & 0xFFF)

    def _layout(self):
        b = self._bpb()
        ss = b["bps"]
        fat_start = b["reserved"] * ss
        root_start = (b["reserved"] + b["nfat"] * b["spf"]) * ss
        root_sectors = (b["rootent"] * 32 + ss - 1) // ss
        data_start_sector = b["reserved"] + b["nfat"] * b["spf"] + root_sectors
        return b, ss, fat_start, root_start, data_start_sector

    def _dir_entry(self, name):
        b, ss, _, root_start, _ = self._layout()
        for i in range(b["rootent"]):
            e = self.flat[root_start + i * 32:root_start + i * 32 + 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5 or (e[11] & 0x08) or (e[11] & 0x10):
                continue
            nm = e[0:8].decode("latin1").rstrip()
            ext = e[8:11].decode("latin1").rstrip()
            fn = nm + ("." + ext if ext else "")
            if fn == name:
                clu = struct.unpack("<H", e[26:28])[0]
                size = struct.unpack("<I", e[28:32])[0]
                return clu, size
        raise KeyError(name)

    def _cluster_flat_offset(self, clu):
        _, ss, _, _, data_start_sector = self._layout()
        return (data_start_sector + (clu - 2)) * ss

    def _cluster_chain(self, clu):
        b, ss, fat_start, _, _ = self._layout()
        fat = self.flat[fat_start:fat_start + b["spf"] * ss]
        chain = []
        while 2 <= clu < 0xFF8:
            chain.append(clu)
            clu = self._fat12_next(fat, clu)
        return chain

    def fat12_file_span(self, name):
        """Return (flat_offset_of_first_cluster, size) for a file."""
        clu, size = self._dir_entry(name)
        return self._cluster_flat_offset(clu), size

    def _fat12_set(self, fat, n, val):
        off = n + n // 2
        cur = fat[off] | (fat[off + 1] << 8)
        if n & 1:
            cur = (cur & 0x000F) | ((val & 0xFFF) << 4)
        else:
            cur = (cur & 0xF000) | (val & 0xFFF)
        fat[off] = cur & 0xFF
        fat[off + 1] = (cur >> 8) & 0xFF

    def file_capacity(self, name):
        """Max bytes `name` can hold WITHOUT relocating (its current cluster
        allocation). The game reads some data files by absolute disk sector, so
        files must not move or change their cluster count."""
        b, ss, *_ = self._layout()
        csize = b["spc"] * ss
        clu, _ = self._dir_entry(name)
        return len(self._cluster_chain(clu)) * csize

    def grow_file(self, name, new_data):
        """Rewrite `name` to `new_data` IN PLACE within its existing clusters
        (never relocates - the game reads some files by absolute sector). Raises
        if `new_data` exceeds the current cluster allocation. Updates dir size."""
        b, ss, fat_start, root_start, data_start = self._layout()
        csize = b["spc"] * ss
        start_clu, _ = self._dir_entry(name)
        chain = self._cluster_chain(start_clu)
        if len(new_data) > len(chain) * csize:
            raise RuntimeError(
                f"{name}: {len(new_data)} bytes exceeds its {len(chain)*csize}-byte "
                f"allocation; it can't grow (read by absolute sector, can't relocate)")
        flat = bytearray(self.flat)
        for i, c in enumerate(chain):
            off = self._cluster_flat_offset(c)
            flat[off:off + csize] = new_data[i * csize:(i + 1) * csize].ljust(csize, b"\x00")
        for i in range(b["rootent"]):
            e = root_start + i * 32
            if flat[e] in (0, 0xE5):
                continue
            nm = bytes(flat[e:e + 8]).decode("latin1").rstrip()
            ext = bytes(flat[e + 8:e + 11]).decode("latin1").rstrip()
            if nm + ("." + ext if ext else "") == name:
                flat[e + 28:e + 32] = struct.pack("<I", len(new_data))
                break
        return D88(self.image).patch_span(0, bytes(flat))

    def extend_file(self, name, new_data):
        """Like grow_file, but ALLOCATES additional free clusters when `new_data`
        needs more than the file's current chain, links them in (both FAT copies),
        and updates the dir size. ONLY for files the engine reads whole via the
        filesystem at true file size (e.g. ITEM.TOS via the DOS 3F count=0xffffffff
        loader) -- never for files read by absolute sector. Returns the new image."""
        b, ss, fat_start, root_start, data_start = self._layout()
        csize = b["spc"] * ss
        fatsz = b["spf"] * ss
        start_clu, _ = self._dir_entry(name)
        chain = self._cluster_chain(start_clu)
        need = max(1, (len(new_data) + csize - 1) // csize)
        flat = bytearray(self.flat)
        fat = bytearray(flat[fat_start:fat_start + fatsz])
        if need > len(chain):
            nent = fatsz * 8 // 12
            free = [c for c in range(2, nent)
                    if self._fat12_next(fat, c) == 0
                    and (data_start + c - 2) * ss + csize <= len(flat)]
            extra = need - len(chain)
            if len(free) < extra:
                raise RuntimeError(f"{name}: need {extra} more clusters, {len(free)} free")
            full = chain + free[:extra]
            for a, nxt in zip(full, full[1:]):
                self._fat12_set(fat, a, nxt)
            self._fat12_set(fat, full[-1], 0xFFF)   # end-of-chain
            chain = full
        for k in range(b["nfat"]):                  # write FAT to all copies
            flat[fat_start + k * fatsz: fat_start + (k + 1) * fatsz] = fat
        for i, c in enumerate(chain):
            off = self._cluster_flat_offset(c)
            flat[off:off + csize] = new_data[i * csize:(i + 1) * csize].ljust(csize, b"\x00")
        for i in range(b["rootent"]):
            e = root_start + i * 32
            if flat[e] in (0, 0xE5):
                continue
            nm = bytes(flat[e:e + 8]).decode("latin1").rstrip()
            ext = bytes(flat[e + 8:e + 11]).decode("latin1").rstrip()
            if nm + ("." + ext if ext else "") == name:
                flat[e + 28:e + 32] = struct.pack("<I", len(new_data))
                break
        return D88(self.image).patch_span(0, bytes(flat))

    def flat_offset_for_file(self, name, file_rel_off):
        """Map a byte offset *within a file* to an absolute flat-image offset,
        following the cluster chain (handles non-contiguous / multi-cluster files)."""
        _, ss, _, _, _ = self._layout()
        clu, size = self._dir_entry(name)
        if not (0 <= file_rel_off < size):
            raise ValueError("offset outside file")
        chain = self._cluster_chain(clu)
        idx = file_rel_off // ss
        within = file_rel_off % ss
        return self._cluster_flat_offset(chain[idx]) + within

    # --- patching ---
    def patch(self, flat_off, new_bytes):
        """Return a new D88 image with new_bytes written at flat_off (length-preserving)."""
        out = bytearray(self.image)
        for i, byte in enumerate(new_bytes):
            fo = flat_off + i
            d88_off = self._flat_to_d88(fo)
            out[d88_off] = byte
        return bytes(out)

    def _flat_to_d88(self, flat_off):
        for flat_start, d88_off, size in self.sectors:
            if flat_start <= flat_off < flat_start + size:
                return d88_off + (flat_off - flat_start)
        raise IndexError(f"flat offset {flat_off} out of range")

    def patch_span(self, flat_off, new_bytes):
        """Length-preserving write of a (possibly large) byte run at flat_off,
        in one pass over the sector map. Returns a new D88 image."""
        out = bytearray(self.image)
        end = flat_off + len(new_bytes)
        for flat_start, d88_off, size in self.sectors:
            lo = max(flat_off, flat_start)
            hi = min(end, flat_start + size)
            if lo < hi:
                dst = d88_off + (lo - flat_start)
                out[dst:dst + (hi - lo)] = new_bytes[lo - flat_off:hi - flat_off]
        return bytes(out)


def read_d88(src):
    return D88(_as_bytes(src))
