Title: Bad default()s
Slug: bad-defaults
Status: draft

I previously wrote about [covariant arrays]({filename}/blog/2019-04-08-ragrets.md), which is a widely
regretted feature among the C# design team. This time I'd like to talk about my personal biggest
regret, `default(T)`.

First, a brief description of the feature for those not familiar. In C# (and .NET in general), all
types are required to have a default or "zero" value. For reference types (classes) this value is
`null`. For value types (structs), this is a value where all of the fields of the struct are the
default value. For the primitive types[^1] (int, double, et al.), the default value is 0 (hence
"zero value"). In C# `default()` is an expression legal in all expression contexts which evaluates
to the default value of the type provided between the parenthesis.

There are two reasons why I dislike the feature. The first is fairly simple: it requires a
particular value to be in the domain of the type which may not be desirable, or which may
not support all of the operations the type is supposed to have. Consider reference types: whether
or not you want it, `null` is a valid value of every reference type. But when you define instance
members on a reference type, those are intended to be callable on all values of that type. But
`null` doesn't support that&mdash;an exception is thrown instead. In short, this may be a
violation of type safety (depending on the definitions of "type safety"), but it's at least a
big weakness in the expressiveness of the type system.

This probably all sounds familiar&mdash;these are the same reasons why `null` is considered
"Tony Hoare's Billion Dollar Mistake" and the motivation around building the C# 8 nullable
reference types feature. That feature in effect tries to reverse some previous decisions by
no longer considering `null` a valid value of all reference types. Of course, this means that
non-null reference types do not have a default value, and indeed `default()` will produce a
warning if one is provided. As you can see, `null` is actually just a particularly annoying
case of the the `default()` problem. Yes, I consider `default()` to be an even bigger problem
than `null`.

It's not just reference types that have the same problem, either. Consider `ImmutableArray&lt;T&rt;`;
this type contains a single reference to an array, and for performance reasons it does not check
if the array is null before accessing an element. Of course, if the `ImmutableArray` is created by
using one of the standard creation functions, it's not possible for the internal array to be null.
If you use `default()`, however, the access function will throw, just like a reference type.

[^1]: Which are value types, but special ones.
