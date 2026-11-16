# Direct-mapped instruction cache

Implement a blocking, read-only cache with two words per line. The cache holds `2**INDEX_W` lines. The CPU can order a global invalidation before reading memory modified elsewhere.

```systemverilog
module cache_controller #(
    parameter int DATA_W = 32,
    parameter int TAG_W = 5,
    parameter int INDEX_W = 2
) (
    input  logic                     clk,
    input  logic                     rst,
    input  logic                     inv_valid,
    output logic                     inv_ready,
    input  logic                     cpu_req_valid,
    output logic                     cpu_req_ready,
    input  logic [TAG_W+INDEX_W:0]   cpu_req_addr,
    output logic                     cpu_rsp_valid,
    input  logic                     cpu_rsp_ready,
    output logic [DATA_W-1:0]        cpu_rsp_data,
    output logic                     mem_req_valid,
    input  logic                     mem_req_ready,
    output logic [TAG_W+INDEX_W-1:0] mem_req_addr,
    input  logic                     mem_rsp_valid,
    output logic                     mem_rsp_ready,
    input  logic [2*DATA_W-1:0]      mem_rsp_data
);
```

Each parameter is positive. CPU addresses are **word** addresses. Their least significant bit is the word offset inside a line, the next `INDEX_W` bits select the direct-mapped index, and the remaining `TAG_W` bits are the tag. A memory request address is the CPU word address with the offset bit removed. In a memory response, word 0 is the low `DATA_W` bits and word 1 is the high `DATA_W` bits.

## Handshakes and transactions

A transfer occurs on a rising edge when the associated valid and ready are both high and reset is low. A sender keeps valid and its payload stable until accepted. Inputs are sampled only on their transfer edges.

1. **Idle.** Assert `inv_ready`. Assert `cpu_req_ready` only if `inv_valid` is low. On an invalidate, clear all cached valid bits and remain idle. Invalidation has no completion response. If the CPU also has a pending request, it can be accepted on a later edge after invalidate releases priority.
2. **CPU request.** Look up the accepted address against the pre-edge cache contents. If the index is valid and its full tag matches, start the CPU response directly after that edge, with the requested word and no memory request. On a miss, save the full request address and start the memory request directly after that edge.
3. **Memory request.** Hold `mem_req_valid` and the line address until accepted. `mem_rsp_ready` is low during this phase. Immediately after the request transfers, deassert request valid and assert response ready.
4. **Memory refill.** Accept one line. On the accepting edge replace data and tag at the requested index and set its valid bit. Start the CPU response directly after that edge with the requested word from the refill. A response asserted early can remain valid until ready. While memory is outstanding, pending CPU requests and invalidations wait.
5. **CPU response.** Hold `cpu_rsp_valid` and its word stable until accepted. Immediately after it transfers, return to idle. Neither a new CPU request nor an invalidation is accepted on the edge that transfers the response.

The five steps specify a single outstanding CPU transaction. The transient request, refill and CPU response phases are disjoint. No memory requests are produced while idle or from a cache hit. Drive `mem_req_addr` to zero whenever `mem_req_valid` is low, and `cpu_rsp_data` to zero whenever `cpu_rsp_valid` is low.

`rst` is active high and synchronous. All ready and valid outputs are zero while it is high. A rising edge with reset high returns the cache to idle, clears all valid bits, and abandons pending transactions. Tag and line data in invalid entries are irrelevant. Endpoints share reset and discard in-flight transactions when reset is sampled. After reset, an abandoned read must be requested again and miss.
