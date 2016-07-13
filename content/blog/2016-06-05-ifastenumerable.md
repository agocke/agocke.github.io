Title: Time to Pay the Piper
Subtitle: Exploring the performance of IEnumerable<T>
Slug: ifastenumerable
Status: draft

As many users of C# know, one of the more common reasons developers prefer
C# to languages like C and C++ is expressivity. Over the past few
releases the language and compiler team have tried to provide more
expressivity through features like `dynamic` and LINQ. Unfortunately, such
features have not been "free," incurring significant run time overhead for
their use.

Recently the compiler team has been taking a closer look at these tradeoffs and
considering a number of language features to help buy back some of that
bare-metal speed. In our experience, one of the biggest causes of performance
issues in C# code is allocating memory, so proposed features include
[ref-locals and ref-returns](https://github.com/dotnet/roslyn/issues/118), and
["replaceable" `Task<T>` for
async](https://github.com/ljw1004/roslyn/blob/features/async-return/docs/specs/feature%20-%20arbitrary%20async%20returns.md),
all of which make it easier to avoid allocating memory. In essence we're
adapting C++'s "pay-for-play" strategy. The idea is that you should be able to
progressively buy into language features such that only using the simple aspects of
features shouldn't necessitate a heavy performance penalty.

Unfortunately, one of the most popular features in C# is one with a pretty bad
pay/play ratio: LINQ. LINQ is loved because it can turn a multi-line `foreach`
and if statement into a quick `array.Where`, but it also turns out that that
short statement can be as much as an order of magnitude worse in performance
than the long-winded `foreach`.

What can we do to "fix" LINQ? The first place to start is probably
`IEnumerable<T>`&mdash;the glue interface that holds all of LINQ together. Of
course, I'm not the only one to try taking on IEnumerable&lt;T>. Jared Parsons,
my lead, wrote [this
article](http://blog.paranoidcoding.com/2014/08/19/rethinking-enumerable.html)
on how to change IEnumerable&lt;T> to a more optimization-friendly structure.
However, Jared's design was lacking one very important thing: an
implementation. I decided to give implementing `IFastEnumerable<T>` a shot.
While I believed that Jared's design would be very fast, I also have to admit
that I hate passing around the extra type parameter, so I've also tried
implementing [my own design with only a single type
parameter](https://github.com/agocke/fast-enumerable/blob/master/IFastEnumerator.cs).

Without further ado, let's take a look at some benchmarks.  These numbers come
from the repository at
[https://github.com/agocke/fast-enumerable](https://github.com/agocke/fast-enumerable).
I examined `IEnumerable<T>` and two possible alternative implementations. The
first alternative is Jared's with a few minor tweaks, while the second is my
own.


    // * Summary *
    BenchmarkDotNet=v0.9.7.0
    OS=OSX
    Processor=?, ProcessorCount=8
    Frequency=1000000000 ticks, Resolution=1.0000 ns, Timer=UNKNOWN
    HostCLR=CORE, Arch=64-bit RELEASE [RyuJIT]
    JitModules=?
    1.0.0-preview1-002702
    Type=Program  Mode=Throughput  Toolchain=Core  
                     Method |        Median |     StdDev |
    ----------------------- |-------------- |----------- |
                    ForLoop |   276.3182 us | 14.0787 us |
                ForEachLoop |   604.3452 us | 16.3732 us |
         ForeachIEnumerable | 1,677.7799 us | 56.6016 us |
    ------------------------------------------------------
             FastEnumerable |   248.7717 us |  6.2044 us |
       MyListFastEnumerable |   304.5593 us | 16.9211 us |
            IFastEnumerable | 1,012.0536 us | 62.9473 us |
     IFastEnumerableGeneric |   250.7948 us |  6.8619 us |
    ------------------------------------------------------
             FastEnumerator |   260.7068 us | 12.6347 us |
       MyListFastEnumerator |   182.6534 us |  2.5559 us |
            IFastEnumerator |   978.0919 us | 16.6613 us |
     IFastEnumeratorGeneric |   452.1760 us | 16.3232 us |
    // ***** BenchmarkRunner: End *****

## IEnumerable&lt;T>

Let's first look at IEnumerable&lt;T>. `ForLoop`, `ForEachLoop`, and
`ForeachIEnumerable` are all based around enumerating the existing `List<T>`
type in various ways. `ForLoop` enumerates `List<T>` using a class index-based
for loop, `ForEachLoop` enumerates using a standard `foreach` loop, and 
`ForeachIEnumerable` enumerates using `foreach` over the `List<T>` cast down
to `IEnumerable<T>`. It turns out that my intuition was correct for these
measurements, so I'll take a brief moment to explain how I ballparked a few
measurements.

First, here are some basic primitives, roughly ordered by expected cost:

1. Register access
2. Integer arithmetic operation in register
3. L1 cache hit
4. Function call
5. L1 cache miss

Let's look at `ForLoop`. This is a simple for-loop over a `List<T>` field.
There's not much here, just an integer counter, a bounds check, an element
access, and an add to a 64-bit accumulator. What would optimal code look
like to me? Probably something like (in asm-pseudocode):


    :::nasm
    xor %rax, %rax
    xor %rcx, %rcx
    mov %rbx, [list.Length]
    loop:
    cmp %rcx, %rbx
    jge done
    add %rax, [list + %rcx]
    add %rcx, 1
    jmp loop
    done:
    ret

What's the probability that this is the code that actually gets generated?
Pretty low, actually. There are a number of assumptions I made that aren't easy
for a compiler to make. While it looks like the iteration over the `List` is
simple, there are a number of indirect calls in the iteration.  First,
`list.Length` and `list[i]` are not simple fields, they're properties.  The
CLR, however, is very good at recognizing these simple properties and inlining
their bodies. But even with inlining, it's not easy to recognize that
`list.Length` is a constant&mdash;the CLR needs to prove that both 1) the loop
body makes no modifications to the length of the array and 2) no other threads
do either. (2) is the tricky part. Without that optimization, we have to issue
a load (hopefully in L1) for every iteration. Similarly, unless we can
prove that the index is less than the array length at every load, we also
have to issue an extra bounds check, possibly two (one for `List<int>` and one
for `int[]`).  Despite the complexity, the CLR actually is often good enough to
make these optimizations, especially if the instance of the `List<int>` is
method-local, making threading and alias analysis much easier.  Regardless, we
can look at this as close to the pinnacle of codegen.

What about `ForeachLoop`? It doesn't look good at first, but `List<T>`
actually takes advantage of a little-known optimization available for `foreach`
included in C#. When running on IEnumerable, `foreach` usually invokes
`IEnumerable<T>.GetEnumerator()` but, if available, `foreach` will instead use
the enumerator returned by a `Enumerator` property, as long as the enumerator
type structurally matches the `IEnumerator` pattern. Aside from saving the
IEnumerable&lt;T> interface dispatch (about 2-4 times more expensive than a
standard call) it also allows the enumerator type to be a struct without boxing
(allocation is also very expensive). With the enumerator as a struct it also
helps with inlining, especially if the fields are promoted to registers. The
main detriment remaining is the `IEnumerator<T>` pattern. Every iteration requires
two method calls and if any of those isn't inlined that can easily double the
cost of an iteration. Unfortuately, that looks like exactly what happened in
the benchmark&mdash;`MoveNext` is not inlined and it looks like the whole loop
time is doubled.

What about `ForeachIEnumerable`? This is the worst of all worlds. There's
interface dispatch and allocation for `GetEnumerator()`, followed by double
interface dispatch for each iteration, along with almost no inlining
opportunity on any path. The results speak for themselves: `ForeachIEnumerable`
is by far the worst result in the benchmark.

## IFastEnumerable

So if IFastEnumerable is so terrible, let's look at some alternatives. First,
Jared's `IFastEnumerableT>`, with a minor modification:

    :::csharp
    public interface IFastEnumerable<TElement, TEnumerator>
    {
      TEnumerator Start { get; }
      TElement TryGetNext(ref TEnumerator enumerator, out bool value);
    }

This version switches the return type and the `out` parameter type, because
`out` will require a memory barrier for some types, but never for `bool`.
Looking at the benchmarks, when the implementation is known statically,
`IFastEnumerable` blazes, beating even `ForLoop` due to better inlining. When
we get down to the bare interface, though, things still don't look great.
`IFastEnumerable` saves significantly due to only a single interface dispatch.
That's about 33% better than `ForeachIEnumerable`, but that's not very high
praise when compared to `ForLoop`. Since it looks like the main cost is
indirection, let's try a little trick to reduce indirection and turn this:

    :::csharp
    void M<T, TEnum>(IFastEnumerable<T, TEnum> ife)
    {
        ...
    }

into this:

    :::csharp
    void M<IFE, T, TEnum>(IFE ife) where IFE : IFastEnumerable<T, TEnum>
    {
        ...
    }

Now, if we get a struct implementing `IFastEnumerable<T, TEnum>` it won't be
boxed and the method calls will be eligible for inlining. It's not a complete
win&mdash;this incurs extra JIT cost. However, JIT cost can be defrayed by NGEN
or crossgen in many cases and the benefits speak for themselves:
`IFastEnumerableGeneric` is almost as fast as `FastEnumerable` and even faster
than `ForLoop`. There is a big problem, though. The compiler is currently
unable to infer the type arguments for this type of call, so the generic
parameters have to be explicitly listed. If we want to use this interface and
pattern it should probably coincide with a change to type inference in the C#
compiler to fix this case (naively, I see no reason why it shouldn't be
inferrable).

## IFastEnumerator

Even with the fix to type inference, I have to admit I'm not satisfied. The
previous method signature is obnoxious enough to type as is, even if I don't
have to deal with any pain at the callsite. This is relevant because a lot
of people use IEnumerable&lt;T> explicitly, writing methods which take and
return IEnumerable&lt;T> types. How can we make this better? Removing that
extra type parameter for the enumerator is certainly a step in the right
direction. Building on Jared's ideas, let's see what that would look like:

    :::csharp
    public interface IFastEnumerator<T>
    {
        T TryGetNext(out bool remaining);
        void Reset();
    }

As you can see, we've cut the extra type parameter, but we've also chosen a
different interface: IFast**Enumerator**&lt;T>. As I looked closer at
IEnumerable&lt;T> I started to feel that the entire interface was unnecessary.
In the current implementation its only purpose was to return an enumerator,
while in Jared's implementation it was eliminated, but at the cost of a type
paraemeter.  I decided to go the other way&mdash;eliminate `IEnumerable<T>`
and just use an `IFastEnumerator<T>` instead. In method calls users can use
an `IFastEnumerator<T>` instead and `foreach` can be extended with a
`GetFastEnumerator()` method, just like `Enumerator`. The real question is,
compared to Jared's implementation, how much will it cost in performance?

Based on the results from `FastEnumerator`, it looks like it costs nothing for
the `foreach` case on a `List<T>` extension method. If we get a little more
bold and pretend `List<T>` will be modified to work with `IFastEnumerator<T>`,
it looks even better, encouraging more inlining bounds-check-elimination and
handily beating out even the `for` loop.

What about the naive `IFastEnumerator<T>` `foreach`? About the same as
IFastEnumerable implementation&mdash;much better than `IEnumerable<T>`, but
still slow. I'm reasonably convinced there's no real win to be had here.

Finally, what about the generic "trick?" If we write our method as follows:

    :::csharp
    void M<T, TEnum>(ref TEnum fastEnum) where TEnum : IFastEnumerator<T>
    {
        ...
    }

type inference can actually figure this out without any modifications. However,
it looks like `IFastEnumeratorGeneric` shows it to be about 80% slower than
`IFastEnumerableGeneric` with the same trick. Why? Looking at the CLR inline
decisions, it seems like everything is being inlined in both implementations.
It looks like we'll have to look at the actual JIT'd assembly. The
`IFastEnumerableGeneric` assembly is
[here](https://gist.github.com/agocke/696b2ab4c1fe8f1c333f81ba9ae3e4f3) and the
`IFastEnumeratorGeneric` assembly is
[here](https://gist.github.com/agocke/c62f28def741e94c6ee23b9fb299838f).

Notably, the basic structure of the codegen for both methods seems identical.
One thing that stands out is that every iteration in IFastEnumeratorGeneric
seems to issue two loads, while `IFastEnumerableGeneric` seems to only take
one. This appears to be because the JIT has hoisted the index variable into a
register for `IFastEnumerableGeneric` and has kept it as a memory access for
`IFastEnumeratorGeneric`. Given the extra overhead for an L1 cache lookup for
each iteration, it seems plausible that this is the cause of the additional
overhead. What's promising, however, is that I don't see any reason why the JIT
would be unable to make the same optimization for `IFastEnumeratorGeneric`, so
with some tweaking they may end up identical in codegen.

What's the verdict?

## Conclusion

Now that we have some hard numbers on the various implementation strategies I
think it will be much easier to decide on a future for IEnumerable&lt;T>.
Personally, I'm pretty pleased with both Jared's and my design, but I'm fairly
convinced that mine is superior for the user, with only minor, fixeable
performance issues in a single scenario.

My next step will probably be to start constructing a PR for the `foreach` loop
to generate the same code I hand-wrote for `IFastEnumerator` and make a NuGet
package so everyone can pull in the new interface and start experimenting on
their own.

The main outstanding work, I think, is the LINQ extension methods. Many can
probably be implemented more efficiently when armed with `IFastEnumerator` than
they can now and that may even have more impact than a fixed `foreach`.
