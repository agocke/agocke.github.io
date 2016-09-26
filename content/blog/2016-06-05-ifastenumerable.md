Title: Time to Pay the Piper
Subtitle: Exploring the performance of IEnumerable<T>
Slug: ifastenumerable
Status: draft

As many C# users know, one of the major reasons developers prefer C# to
languages like C and C++ is expressivity. As language designers the C# language
team has often embraced this goal and over the past few releases has tried to
provide more expressivity through features like `dynamic` and LINQ.
Unfortunately, such features have not been "free," incurring significant run-time
overhead for their use.

Recently we've been taking a closer look at these tradeoffs and
considering a number of language features to help buy back some of that
bare-metal speed. In our experience, allocating memory is one of the biggest
causes of performance issues in C# code, so proposed features include
[ref-locals and ref-returns](https://github.com/dotnet/roslyn/issues/118), and
["replaceable" `Task<T>` for
async](https://github.com/ljw1004/roslyn/blob/features/async-return/docs/specs/feature%20-%20arbitrary%20async%20returns.md),
all of which make it easier to avoid allocating memory. In essence we're
adapting C++'s "pay-for-play" strategy: you should only pay for the cost of the
aspects of the feature you actually use. If you just use simple aspects of a
feature you shouldn't have to pay for all the possible corner cases of the
compilicated aspects.

Unfortunately, one of the most popular features in C# is one with a pretty bad
pay/play ratio: LINQ. LINQ is loved because it can turn a multi-line `foreach`
and if statement into a quick `array.Where`, but it also turns out that that
short statement can be as much as an order of magnitude worse in performance
than the long-winded `foreach`.

So what can we do to make simple LINQ uses simple? The place to start is
probably `IEnumerable<T>`&mdash;the glue interface that holds all of LINQ
together. `IEnumerable<T>` makes things simple by hiding most of LINQ's 
complexity behind a simple interface, but it means that we can often make
fewer optimizations since we don't know what's hiding behind that interface. Of
course, I'm not the only one to try taking on IEnumerable&lt;T>. Jared Parsons,
my lead, wrote [this
article](http://blog.paranoidcoding.com/2014/08/19/rethinking-enumerable.html)
on how to change IEnumerable&lt;T> to a more optimization-friendly structure.
His article also details some of the performance problems with the existing
interface.

However, Jared's design was lacking one very important thing: an
implementation. I decided to give implementing `IFastEnumerable<T>` a shot.
While I thought Jared's design would be fast, I also have to admit
that I hated passing around the extra type parameter, so I also tried
implementing [my own design with only a single type
parameter](https://github.com/agocke/fast-enumerable/blob/master/IFastEnumerator.cs).
If you're impatient, you can find all of the test cases and the raw output
data at 
[https://github.com/agocke/fast-enumerable](https://github.com/agocke/fast-enumerable).

## IEnumerable&lt;T>

Before we get into numbers, let's quickly look at what some test cases look
like and how `IEnumerable<T>` fits in. In these benchmarks we'll be measuring
a simple accumulator that iterates over a large list of integers and adds each
element of the list to a sum variable, as below:

```csharp
long total = 0;
for (int i = 0; i < _list.Count; i++)
{
    total += _list[i];
}
```

Why this test? By choosing a simple operation, like a single addition, and a
large list we minimize the role of the inner operation and emphasize the cost
of iterating. In other words, iteration should be by far the most dominant cost
in this program, so the speed of iteration should matter quite a lot for the
speed of the program.

Now that we have our for-loop baseline, we can incorporate `IEnumerable<T>` into
the mix. We'll do this in two ways. First, we'll use the same list, but rather
than iterating with a `for` loop, we'll use a `foreach` loop. Second, we'll
also use a `foreach` loop for iterating, but this time we'll cast the list to
an `IEnumerable<T>` before iterating. Why the cast? It turns out that `foreach`
has some tricks up its sleave when it's run over concrete list type that allows
for more optimizations. Casting to `IEnumerable<T>` means that all operations
must go through the interface and `foreach` can't pull any tricks.

Before I looked at the numbers, my intuition was that it would play out something
like this: the `for` loop would be fastest, followed by the simple `foreach` at
something like a 1-3x cost, followed by the `foreach` over `IEnumerable<T>` at a 
5-10x cost. So what were the actual numbers?

```
                 Method |        Median |     StdDev |
----------------------- |-------------- |----------- |
                ForLoop |   276.3182 us | 14.0787 us |
            ForEachLoop |   604.3452 us | 16.3732 us |
     ForeachIEnumerable | 1,677.7799 us | 56.6016 us |
```

Pretty good! So how did I come up with my guess? For that we'll have to take a
brief digression into the fundamentals of computer hardware and the CLR.

First, here are some basic primitives, roughly ordered by expected cost:

1. Register access
2. Integer arithmetic operation in register
3. L1 cache hit
4. Function call
5. L1 cache miss

Let's look at `ForLoop`. This is a simple for-loop over a `List<T>` field, as
shown above. There's not much here, just an integer counter,
a bounds check, an element access, and an add to a 64-bit accumulator. What
would optimal code look like? Probably something like (in asm-pseudocode):

    :::nasm
    xor %rax, %rax              ; total = 0
    xor %rcx, %rcx              ; i = 0
    mov %rbx, [list.Length]     ; Store the length in a register
    loop:
    cmp %rcx, %rbx              ; if (i >= length) goto done;
    jge done                    ; else
    add %rax, [list + %rcx]     ;   total += list[i]
    add %rcx, 1                 ;   i++
    jmp loop                    ; goto loop;
    done:
    ret

What's the probability that this is the code that actually gets generated?
Pretty low, actually. There are a number of assumptions I made that aren't easy
for a compiler to make. While it looks like the iteration over the list is
simple, there are a number of indirect calls in the iteration.  First,
`list.Length` and `list[i]` are not simple fields, they're properties, which
means they're function calls under the hood. It just so happens that all they
do is return a field or piece of memory, but theoretically they could be more
complicated. The CLR, however, is very good at recognizing these simple
properties and inlining their bodies. But even with inlining, it's not easy to
recognize that `list.Length` is a constant&mdash;the CLR needs to prove that
both 1) the loop body makes no modifications to the length of the array and 2)
no other threads do either. (2) is the tricky part. Without that optimization,
we have to issue a load (hopefully in L1) for every iteration. Similarly,
unless we can prove that the index is less than the array length at every load,
we also have to issue an extra bounds check, possibly two (one for
`List<int>.this[]` and one for the `int[]` actually holding the data). Despite
the complexity, the CLR actually is often good enough to make these
optimizations, especially if the instance of the `List<int>` is method-local,
making threading and alias analysis much easier.  Regardless, we can look at
the CLR's attempt as close to the pinnacle of codegen.

What about `ForeachLoop`? It doesn't look good at first but, as I mentioned
earlier, `foreach` has its little tricks. `List<T>` actually takes advantage
of a little-known optimization available for `foreach` included in C#: when
running on `IEnumerable<T>`, `foreach` normally invokes
`IEnumerable<T>.GetEnumerator()`. But, if the type has a method named
`GetEnumerator` and that method returns a type that *structurally* matches the
`IEnumerator<T>` interface, `foreach` will use that instead. `List<T>` has all
of this, so this path is used whenever `foreach` is called on a list directly.
Aside from saving the `IEnumerable<T>` interface dispatch (about 2-4 times more
expensive than a standard call) it also allows the enumerator type to be a
struct without boxing (allocation is also very expensive). With the enumerator
as a struct it also helps with inlining, especially if the fields are promoted
to registers. The main detriment remaining is the `IEnumerator<T>` pattern.
Every iteration requires two method calls and if any of those isn't inlined
that can easily double the cost of an iteration, meaning a 2-3x total penalty.
Unfortuately, that looks like exactly what happened in the
benchmark&mdash;`MoveNext` is not inlined and the whole loop time is doubled.

What about `ForeachIEnumerable`? This is the worst of all worlds. There's
interface dispatch and allocation for `GetEnumerator()`, followed by double
interface dispatch for each iteration, along with almost no inlining
opportunity on any path. The results speak for themselves: `ForeachIEnumerable`
is by far the worst result in the benchmark.

## IFastEnumerable&lt;T>

So how can we improve `IEnumerable<T>`? As Jared points out in his post,
interface dispatch is the root of many of our problems. Just a `calli` alone is
~2x slower than a virtual call, which is about 2x slower than an ordinary method
call. Both Jared's and my design try to address this, Jared's by passing around
the enumerator type as type parameter, rather than using an interface like
`IEnumerator<T>`. Let's first look at Jared's `IFastEnumerable<T>`, with a
minor modification:

    :::csharp
    public interface IFastEnumerable<TElement, TEnumerator>
    {
      TEnumerator Start { get; }
      TElement TryGetNext(ref TEnumerator enumerator, out bool hasValue);
    }

This version uses the element as the return value and the ending sentinal
as an `out` parameter, insetad of the other way araound, because `out` will
require a memory barrier for some types, but never for `bool`. Let's see how
fairs:

    :::csharp
                    Method  |        Median |     StdDev |
    ----------------------- |-------------- |----------- |
                    ForLoop |   276.3182 us | 14.0787 us |
                ForEachLoop |   604.3452 us | 16.3732 us |
        ForeachIEnumerable  | 1,677.7799 us | 56.6016 us |
    ------------------------------------------------------
     ForeachFastEnumerable  |   248.7717 us |  6.2044 us |
            IFastEnumerable | 1,012.0536 us | 62.9473 us |
    IFastEnumerableGeneric  |   250.7948 us |  6.8619 us |

You'll notice a couple different things about this benchmark set compared to
the one for `IEnumerable`. First, you'll note that `ForLoop` isn't included
(because it won't change). Second, you'll notice that there are two entries in
place of `ForeachIEnumerable`: `ForeachFastEnumerable` and
`IFastEnumerableGeneric`. We'll get to `IFastEnumerableGeneric` soon, but 
`ForeachFastEnumerable` is essentially equivalent to `ForEachLoop`, but using
a type that implements `IFastEnumerable` instead of `IENumerable`.

This reflects two different ways of adding support
for `IFastEnumerable<T>` to existing an existing `List` type. On the one hand, you could implement a
separate type that implements `IFastEnumerable` and delegates to an underlying
existing List. On the other, you can reimplement `List` such that it implements 
`IFastEnumerable`, essentially pretending that the framework has been updated
to take advantage of the new interface. 

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

This rewrite corresponds to the aforementiond `IFastEnumerableGeneric` numbers.
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

## IFastEnumerator&lt;T>

Even with the fix to type inference, I have to admit I'm not satisfied. The
previous method signature is obnoxious enough to type as is, even if I don't
have to deal with any pain at the callsite. This is relevant because a lot
of people use `IEnumerable<T>` explicitly, writing methods which take and
return `IEnumerable<T>` types. How can we make this better? Removing that
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

                     Method |        Median |     StdDev |
    ----------------------- |-------------- |----------- |
                    ForLoop |   276.3182 us | 14.0787 us |
                ForEachLoop |   604.3452 us | 16.3732 us |
         ForeachIEnumerable | 1,677.7799 us | 56.6016 us |
    ------------------------------------------------------
      ForeachFastEnumerable |   248.7717 us |  6.2044 us |
            IFastEnumerable | 1,012.0536 us | 62.9473 us |
     IFastEnumerableGeneric |   250.7948 us |  6.8619 us |
    ------------------------------------------------------
      ForeachFastEnumerator |   260.7068 us | 12.6347 us |
       MyListFastEnumerator |   182.6534 us |  2.5559 us |
            IFastEnumerator |   978.0919 us | 16.6613 us |
     IFastEnumeratorGeneric |   452.1760 us | 16.3232 us |

Most of these labels should be self-explanatory, but there's a new item in the
list: `MyListFastEnumerator`. This is very similar to `ForeachFastEnumerator`,
but rather than delegating to an existing `List` type, this implementation uses
a handwritten `List` type, pretending that we update `List<T>` with an
implementation for `IFastEnumerator`.

Based on the results from `ForeachFastEnumerator`, it looks like it costs
nothing for the `foreach` case on a `List<T>` extension method. If we get a
little more bold and pretend `List<T>` will be modified to work with
`IFastEnumerator<T>`, `MyListFastEnumerator` is even better, encouraging more
inlining bounds-check-elimination and beating out even the simple `for` loop.

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
We'll have to look at the actual JIT'd assembly. The
`IFastEnumerableGeneric` assembly is
[here](https://gist.github.com/agocke/696b2ab4c1fe8f1c333f81ba9ae3e4f3) and the
`IFastEnumeratorGeneric` assembly is
[here](https://gist.github.com/agocke/c62f28def741e94c6ee23b9fb299838f).

Notably, the basic structure of the codegen for both methods seems identical.
One thing that stands out is that every iteration in `IFastEnumeratorGeneric`
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
think it will be much easier to decide on a future for `IEnumerable<T>`.
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
