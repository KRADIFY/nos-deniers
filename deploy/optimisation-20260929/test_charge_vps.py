"""50 simultaneous, read-only budget consultations against the new VPS staging proxy."""
import subprocess

REMOTE = r'''import concurrent.futures, json, ssl, statistics, time, urllib.error, urllib.request
from urllib.parse import urlencode

context = ssl._create_unverified_context()  # The request is strictly localhost on the VPS.
cases = [
    dict(start=2023, end=2025, measure='CP', budget='BG'),
    dict(start=2017, end=2022, measure='AE', budget='BG'),
    dict(start=2020, end=2020, measure='AE', budget='BG', scope='SB/176'),
    dict(start=2022, end=2024, measure='CP', budget='CAS'),
    dict(start=2020, end=2022, measure='CP', budget='BG', constant='1', base=2025),
    dict(start=2023, end=2025, measure='CP', budget='BG', exclude='["TA/174"]'),
]

def request(index):
    query = urlencode(cases[index % len(cases)])
    start = time.monotonic()
    req = urllib.request.Request('https://127.0.0.1/api/explorer?' + query,
                                 headers={'Host': 'budget.lexmachine.net', 'Accept-Encoding': 'gzip'})
    try:
        with urllib.request.urlopen(req, timeout=120, context=context) as response:
            body, code = response.read(), response.status
    except urllib.error.HTTPError as exc:
        body, code = exc.read(), exc.code
    except Exception as exc:
        return 0, time.monotonic() - start, 0, str(exc)
    return code, time.monotonic() - start, len(body), body[:100].startswith(b'<html')

for i in range(len(cases)):
    assert request(i)[0] == 200
start = time.monotonic()
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
    results = list(pool.map(request, range(50)))
times = sorted(item[1] for item in results)
report = {
    'requests': len(results),
    'concurrency': 50,
    'http_200': sum(item[0] == 200 for item in results),
    'html_instead_of_json': sum(item[3] for item in results),
    'elapsed_wall_seconds': round(time.monotonic() - start, 3),
    'latency_p50_seconds': round(statistics.median(times), 3),
    'latency_p95_seconds': round(times[int(len(times) * .95) - 1], 3),
    'latency_max_seconds': round(max(times), 3),
    'minimum_response_bytes': min(item[2] for item in results),
    'status_counts': {str(code): sum(item[0] == code for item in results) for code in sorted({item[0] for item in results})},
    'failed_examples': [(i, result[0], result[3]) for i, result in enumerate(results) if result[0] != 200][:8],
}
print(json.dumps(report, ensure_ascii=False), flush=True)
assert report['http_200'] == 50 and report['html_instead_of_json'] == 0
'''

if __name__ == '__main__':
    subprocess.run(['ssh', '-o', 'BatchMode=yes', 'root@5.189.145.254', 'python3 -'],
                   input=REMOTE.encode(), check=True)
