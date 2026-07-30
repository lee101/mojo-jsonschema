"""C ABI for batched validation of columnar JSON values."""

from std.algorithm.functional import parallelize
from std.sys.info import simd_width_of as simdwidthof


comptime IPtr = UnsafePointer[Int64, AnyOrigin[mut=True]]
comptime FPtr = UnsafePointer[Float64, AnyOrigin[mut=True]]
comptime W = simdwidthof[DType.float64]()
comptime PARALLEL_THRESHOLD = 262144
comptime ROWS_PER_TASK = 16384


def _validate_range(
    start: Int,
    end: Int,
    tags: IPtr,
    numbers: FPtr,
    lengths: IPtr,
    valid: IPtr,
    type_masks: IPtr,
    flags: IPtr,
    min_lengths: IPtr,
    max_lengths: IPtr,
    minimums: FPtr,
    maximums: FPtr,
    multiples: FPtr,
    nrows: Int,
    nprops: Int,
):
    var vector_end = start + ((end - start) // W) * W
    for row in range(start, vector_end, W):
        valid.store(row, SIMD[DType.int64, W](1))
    for row in range(vector_end, end):
        valid[row] = 1

    for prop in range(nprops):
        var rule = flags[prop]
        var expected = type_masks[prop]
        var base = prop * nrows

        if (rule & 16) != 0:
            for row in range(start, end):
                if valid[row] == 0:
                    continue
                var index = base + row
                var tag = tags[index]
                if tag == 0:
                    if (rule & 128) != 0:
                        valid[row] = 0
                    continue
                if expected != 0 and (tag & expected) == 0:
                    valid[row] = 0
                    continue
                if (tag & 12) != 0:
                    var value = numbers[index]
                    if (rule & 1) != 0 and value < minimums[prop]:
                        valid[row] = 0
                        continue
                    if (rule & 2) != 0 and value > maximums[prop]:
                        valid[row] = 0
                        continue
                    if (rule & 4) != 0 and value <= minimums[prop]:
                        valid[row] = 0
                        continue
                    if (rule & 8) != 0 and value >= maximums[prop]:
                        valid[row] = 0
                        continue
                    var divisor = multiples[prop]
                    var quotient = value / divisor
                    if Float64(Int(quotient)) != quotient:
                        valid[row] = 0
                        continue
                if (tag & 48) != 0:
                    var length = lengths[index]
                    if (rule & 32) != 0 and length < min_lengths[prop]:
                        valid[row] = 0
                        continue
                    if (rule & 64) != 0 and length > max_lengths[prop]:
                        valid[row] = 0
            continue

        for row in range(start, vector_end, W):
            var index = base + row
            var current = valid.load[width=W](row)
            var tag = tags.load[width=W](index)
            var ok = current.ne(SIMD[DType.int64, W](0))
            if (rule & 128) != 0:
                ok &= tag.ne(SIMD[DType.int64, W](0))
            if expected != 0:
                ok &= tag.eq(SIMD[DType.int64, W](0)) | (
                    (tag & SIMD[DType.int64, W](expected)).ne(
                        SIMD[DType.int64, W](0)
                    )
                )

            var numeric = (tag & SIMD[DType.int64, W](12)).ne(
                SIMD[DType.int64, W](0)
            )
            if (rule & 1) != 0:
                ok &= ~numeric | (
                    numbers.load[width=W](index).ge(
                        SIMD[DType.float64, W](minimums[prop])
                    )
                )
            if (rule & 2) != 0:
                ok &= ~numeric | (
                    numbers.load[width=W](index).le(
                        SIMD[DType.float64, W](maximums[prop])
                    )
                )
            if (rule & 4) != 0:
                ok &= ~numeric | (
                    numbers.load[width=W](index).gt(
                        SIMD[DType.float64, W](minimums[prop])
                    )
                )
            if (rule & 8) != 0:
                ok &= ~numeric | (
                    numbers.load[width=W](index).lt(
                        SIMD[DType.float64, W](maximums[prop])
                    )
                )

            var sized = (tag & SIMD[DType.int64, W](48)).ne(
                SIMD[DType.int64, W](0)
            )
            if (rule & 32) != 0:
                ok &= ~sized | (
                    lengths.load[width=W](index).ge(
                        SIMD[DType.int64, W](min_lengths[prop])
                    )
                )
            if (rule & 64) != 0:
                ok &= ~sized | (
                    lengths.load[width=W](index).le(
                        SIMD[DType.int64, W](max_lengths[prop])
                    )
                )
            valid.store(
                row,
                ok.select(
                    SIMD[DType.int64, W](1), SIMD[DType.int64, W](0)
                ),
            )

        for row in range(vector_end, end):
            if valid[row] == 0:
                continue
            var index = base + row
            var tag = tags[index]
            if tag == 0:
                if (rule & 128) != 0:
                    valid[row] = 0
                continue
            if expected != 0 and (tag & expected) == 0:
                valid[row] = 0
                continue
            if (tag & 12) != 0:
                var value = numbers[index]
                if (rule & 1) != 0 and value < minimums[prop]:
                    valid[row] = 0
                    continue
                if (rule & 2) != 0 and value > maximums[prop]:
                    valid[row] = 0
                    continue
                if (rule & 4) != 0 and value <= minimums[prop]:
                    valid[row] = 0
                    continue
                if (rule & 8) != 0 and value >= maximums[prop]:
                    valid[row] = 0
                    continue
            if (tag & 48) != 0:
                var length = lengths[index]
                if (rule & 32) != 0 and length < min_lengths[prop]:
                    valid[row] = 0
                    continue
                if (rule & 64) != 0 and length > max_lengths[prop]:
                    valid[row] = 0


@export("mjs_validate_flat")
def mjs_validate_flat(
    tags_addr: Int,
    numbers_addr: Int,
    lengths_addr: Int,
    valid_addr: Int,
    type_masks_addr: Int,
    flags_addr: Int,
    min_lengths_addr: Int,
    max_lengths_addr: Int,
    minimums_addr: Int,
    maximums_addr: Int,
    multiples_addr: Int,
    nrows: Int,
    nprops: Int,
    use_parallel: Int,
) abi("C") -> Int:
    if (
        nrows <= 0
        or nprops <= 0
        or nprops > 9223372036854775807 // nrows
        or tags_addr == 0
        or numbers_addr == 0
        or lengths_addr == 0
        or valid_addr == 0
        or type_masks_addr == 0
        or flags_addr == 0
        or min_lengths_addr == 0
        or max_lengths_addr == 0
        or minimums_addr == 0
        or maximums_addr == 0
        or multiples_addr == 0
    ):
        return 1

    var tags = IPtr(unsafe_from_address=tags_addr)
    var numbers = FPtr(unsafe_from_address=numbers_addr)
    var lengths = IPtr(unsafe_from_address=lengths_addr)
    var valid = IPtr(unsafe_from_address=valid_addr)
    var type_masks = IPtr(unsafe_from_address=type_masks_addr)
    var flags = IPtr(unsafe_from_address=flags_addr)
    var min_lengths = IPtr(unsafe_from_address=min_lengths_addr)
    var max_lengths = IPtr(unsafe_from_address=max_lengths_addr)
    var minimums = FPtr(unsafe_from_address=minimums_addr)
    var maximums = FPtr(unsafe_from_address=maximums_addr)
    var multiples = FPtr(unsafe_from_address=multiples_addr)

    if nrows < PARALLEL_THRESHOLD or use_parallel == 0:
        _validate_range(
            0,
            nrows,
            tags,
            numbers,
            lengths,
            valid,
            type_masks,
            flags,
            min_lengths,
            max_lengths,
            minimums,
            maximums,
            multiples,
            nrows,
            nprops,
        )
        return 0

    var num_tasks = (nrows + ROWS_PER_TASK - 1) // ROWS_PER_TASK

    def work(task: Int) capturing:
        var start = task * ROWS_PER_TASK
        var end = min(start + ROWS_PER_TASK, nrows)
        _validate_range(
            start,
            end,
            tags,
            numbers,
            lengths,
            valid,
            type_masks,
            flags,
            min_lengths,
            max_lengths,
            minimums,
            maximums,
            multiples,
            nrows,
            nprops,
        )

    parallelize[work](num_tasks)
    return 0
