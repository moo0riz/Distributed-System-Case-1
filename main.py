"""Program sederhana (single vs multi reader thread):
- Printer thread: mengambil data dari queue lalu menampilkan ke layar
- Reader: bisa 1 thread (single) atau beberapa thread paralel (multi)

Multi-reader:
File dibagi ke beberapa rentang baris (chunk). Tiap reader thread membaca chunk
masing-masing dan mengirim hasil ke queue.
Dampak: output bisa tidak berurutan karena data datang dari thread berbeda.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Optional


@dataclass(frozen=True)
class Message:
    line_no: int
    text: str


def reader_single(file_path: Path, q: Queue[Optional[Message]]) -> None:
    with file_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            q.put(Message(i, line.rstrip("\n")))


def reader_chunk(file_path: Path, start_line: int, end_line: int, q: Queue[Optional[Message]]) -> None:
    """Baca file baris ke [start_line..end_line] (inklusif), 1-based."""
    with file_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if i < start_line:
                continue
            if i > end_line:
                break
            q.put(Message(i, line.rstrip("\n")))


def printer(q: Queue[Optional[Message]]) -> None:
    """Printer thread.

    Supaya output tidak kebanyakan saat file besar, default-nya hanya menampilkan
    beberapa baris pertama dan terakhir, lalu sisanya di-skip.
    """

    max_head = 10
    max_tail = 10
    tail: list[Message] = []
    printed_head = 0
    skipped = 0

    while True:
        item = q.get()
        if item is None:
            break

        if printed_head < max_head:
            print(f"{item.line_no}: {item.text}")
            printed_head += 1
            continue

        # Simpan tail ring-buffer
        if len(tail) < max_tail:
            tail.append(item)
        else:
            tail.pop(0)
            tail.append(item)
        skipped += 1

    if skipped > 0:
        print(f"... ({skipped} baris tidak ditampilkan) ...")
    for m in tail:
        print(f"{m.line_no}: {m.text}")


def _count_lines(file_path: Path) -> int:
    with file_path.open("r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def run_single(file_path: Path) -> float:
    q: Queue[Optional[Message]] = Queue()
    t_print = threading.Thread(target=printer, args=(q,), name="printer")
    t_read = threading.Thread(target=reader_single, args=(file_path, q), name="reader-single")

    start = time.perf_counter()
    t_print.start()
    t_read.start()

    t_read.join()
    q.put(None)  # stop printer
    t_print.join()
    return time.perf_counter() - start


def run_multi(file_path: Path, num_readers: int = 4) -> float:
    total_lines = _count_lines(file_path)
    if total_lines == 0:
        return 0.0

    q: Queue[Optional[Message]] = Queue()
    t_print = threading.Thread(target=printer, args=(q,), name="printer")

    chunk_size = (total_lines + num_readers - 1) // num_readers
    readers: list[threading.Thread] = []

    for idx in range(num_readers):
        start_line = idx * chunk_size + 1
        end_line = min((idx + 1) * chunk_size, total_lines)
        if start_line > total_lines:
            break
        readers.append(
            threading.Thread(
                target=reader_chunk,
                args=(file_path, start_line, end_line, q),
                name=f"reader-{idx + 1}",
            )
        )

    start = time.perf_counter()
    t_print.start()
    for t in readers:
        t.start()

    for t in readers:
        t.join()

    q.put(None)  # stop printer setelah semua reader selesai
    t_print.join()
    return time.perf_counter() - start


def main() -> None:
    file_path = Path("data.txt")

    # Buat data yang banyak agar perbedaan waktu lebih terlihat.
    # Ditulis ulang jika file belum ada ATAU ukurannya masih kecil.
    target_lines = 200_000
    min_bytes = 1_000_000
    if (not file_path.exists()) or (file_path.stat().st_size < min_bytes):
        file_path.write_text(
            "\n".join(str(i) for i in range(1, target_lines + 1)) + "\n",
            encoding="utf-8",
        )

    print("== Singlethread reader ==")
    t_single = run_single(file_path)
    print(f"Singlethread ({t_single:.3f}s)\n")

    print("== Multithread reader (2 threads) ==")
    t_multi = run_multi(file_path, num_readers=2)
    print(f"Multithread ({t_multi:.3f}s)")


if __name__ == "__main__":
    main()
