import copy
import functools

from . import optics

# we skip all the augmented artithmetic methods because the point of the
# lenses library is not to mutate anything
transparent_dunders = ('''
    __lt__ __le__ __eq__ __ne__ __gt__ __ge__

    __add__ __sub__ __mul__ __matmul__ __truediv__
    __floordiv__ __div__ __mod__ __divmod__ __pow__
    __lshift__ __rshift__ __and__ __xor__ __or__

    __radd__ __rsub__ __rmul__ __rmatmul__ __rtruediv__
    __rfloordiv__ __rdiv__ __rmod__ __rdivmod__ __rpow__
    __rlshift__ __rrshift__ __rand__ __rxor__ __ror__

    __neg__ __pos__ __invert__
''').split()


def _carry_op(name):
    def operation(self, *args, **kwargs):
        return self.modify(lambda a: getattr(a, name)(*args, **kwargs))

    doc = 'Equivalent to `self.call({!r}, *args, **kwargs))`'
    operation.__name__ = name
    operation.__doc__ = doc.format(name)
    return operation


def _add_extra_methods(cls):
    for dunder in transparent_dunders:
        setattr(cls, dunder, _carry_op(dunder))

    return cls


@_add_extra_methods
class Lens(object):
    'A user-friendly object for interacting with the lenses library'
    __slots__ = ['state', 'lens']

    def __init__(self, state=None, lens=None):
        if lens is None:
            lens = optics.TrivialIso()
        self.state = state
        self.lens = lens

    def __repr__(self):
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.state, self.lens)

    def _assert_bound(self, name):
        if self.state is None:
            raise ValueError('{} requires a bound lens'.format(name))

    def _assert_unbound(self, name):
        if self.state is not None:
            raise ValueError('{} requires an unbound lens'.format(name))

    def get(self, state=None):
        '''Get the first value focused by the lens.

            >>> from lenses import lens
            >>> lens([1, 2, 3]).get()
            [1, 2, 3]
            >>> lens([1, 2, 3])[0].get()
            1
        '''
        if state is not None:
            self = self.bind(state)
        self._assert_bound('Lens.get')
        return self.lens.to_list_of(self.state)[0]

    def get_all(self, state=None):
        '''Get multiple values focused by the lens. Returns them as
        a list.

            >>> from lenses import lens
            >>> lens([1, 2, 3])[0].get_all()
            [1]
            >>> lens([1, 2, 3]).both_().get_all()
            [1, 2]
        '''
        if state is not None:
            self = self.bind(state)
        self._assert_bound('Lens.get_all')
        return self.lens.to_list_of(self.state)

    def get_monoid(self, state=None):
        '''Get the values focused by the lens, merging them together by
        treating them as a monoid. See `lenses.typeclass.mappend`.

            >>> from lenses import lens
            >>> lens([[], [1], [2, 3]]).each_().get_monoid()
            [1, 2, 3]
        '''
        if state is not None:
            self = self.bind(state)
        self._assert_bound('Lens.get_monoid')
        return self.lens.view(self.state)

    def set(self, newvalue, state=None):
        '''Set the focus to `newvalue`.

            >>> from lenses import lens
            >>> lens([1, 2, 3])[1].set(4)
            [1, 4, 3]
        '''
        if state is not None:
            self = self.bind(state)
        self._assert_bound('Lens.set')
        return self.lens.set(self.state, newvalue)

    def modify(self, func, state=None):
        '''Apply a function to the focus.

            >>> from lenses import lens
            >>> lens([1, 2, 3])[1].modify(str)
            [1, '2', 3]
            >>> lens([1, 2, 3])[1].modify(lambda n: n + 10)
            [1, 12, 3]
        '''
        if state is not None:
            self = self.bind(state)
        self._assert_bound('Lens.modify')
        return self.lens.over(self.state, func)

    def call(self, method_name, *args, **kwargs):
        '''Call a method on the focus. The method must return a new
        value for the focus.

            >>> from lenses import lens
            >>> lens(['alpha', 'beta', 'gamma'])[2].call('upper')
            ['alpha', 'beta', 'GAMMA']

        As a shortcut, you can include the name of the method you want
        to call immediately after `call_`:

            >>> lens(['alpha', 'beta', 'gamma'])[2].call_upper()
            ['alpha', 'beta', 'GAMMA']
        '''
        if 'state' in kwargs:
            self = self.bind(kwargs['state'])
            del kwargs['state']

        def func(a):
            return getattr(a, method_name)(*args, **kwargs)

        return self.modify(func)

    def call_mut(self, method_name, *args, **kwargs):
        '''Call a method on the focus that will mutate it in place.
        Works by making a deep copy of the focus before calling the
        mutating method on it. The return value of that method is ignored.
        You can pass a keyword argument shallow=True to only make a
        shallow copy.

            >>> from lenses import lens
            >>> lens([[3, 1, 2], [5, 4]])[0].call_mut('sort')
            [[1, 2, 3], [5, 4]]

        As a shortcut, you can include the name of the method you want
        to call immediately after `call_mut_`:

            >>> lens([[3, 1, 2], [5, 4]])[0].call_mut_sort()
            [[1, 2, 3], [5, 4]]
        '''
        if 'state' in kwargs:
            self = self.bind(kwargs['state'])
            del kwargs['state']

        shallow = False
        if 'shallow' in kwargs:
            shallow = kwargs['shallow']
            del kwargs['shallow']

        def func(a):
            a = copy.copy(a) if shallow else copy.deepcopy(a)
            getattr(a, method_name)(*args, **kwargs)
            return a

        return self.modify(func)

    def construct(self, focus=None):
        '''Construct a state given a focus.'''
        if focus is not None:
            self = self.bind(focus)
        self._assert_bound('Lens.construct')
        return self.lens.re().view(self.state)

    def add_lens(self, other):
        '''Refine the current focus of this lens by composing it with
        another lens object. Can be a `lenses.optics.LensLike` or an
        unbound `lenses.Lens`.

            >>> from lenses import lens
            >>> second_first = lens()[1][0]
            >>> lens([[0, 1], [2, 3]]).add_lens(second_first).get()
            2
        '''
        if isinstance(other, optics.LensLike):
            return Lens(self.state, self.lens.compose(other))
        elif isinstance(other, Lens):
            other._assert_unbound('Lens.add_lens')
            return Lens(self.state, self.lens.compose(other.lens))
        else:
            raise TypeError('''Cannot add lens of type {!r}.'''
                            .format(type(other)))

    def bind(self, state):
        '''Bind this lens to a specific `state`. Raises `ValueError`
        when the lens has already been bound.

            >>> from lenses import lens
            >>> lens()[1].bind([1, 2, 3]).get()
            2
        '''
        self._assert_unbound('Lens.bind')
        return Lens(state, self.lens)

    def flip(self):
        '''Flips the direction of the lens. The lens must be unbound
        and all the underlying operations must be isomorphisms.

            >>> from lenses import lens
            >>> json_encoder = lens().decode_().json_().flip()
            >>> json_encoder.bind(['hello', 'world']).get()  # doctest: +SKIP
            b'["hello", "world"]'
        '''
        self._assert_unbound('Lens.flip')
        return Lens(self.state, self.lens.from_())

    def both_(self):
        '''A traversal that focuses both items [0] and [1].

            >>> from lenses import lens
            >>> lens().both_()
            Lens(None, BothTraversal())
            >>> lens([1, 2, 3]).both_().get_all()
            [1, 2]
            >>> lens([1, 2, 3]).both_().set(4)
            [4, 4, 3]
        '''
        return self.add_lens(optics.BothTraversal())

    def decode_(self, encoding='utf-8', errors='strict'):
        '''An isomorphism that decodes and encodes its focus on the
        fly. Lets you focus a byte string as a unicode string. The
        arguments have the same meanings as `bytes.decode`. Analogous to
        `bytes.decode`.

            >>> from lenses import lens
            >>> lens().decode_(encoding='utf8')
            Lens(None, DecodeIso('utf8', 'strict'))
            >>> lens(b'hello').decode_().get()  # doctest: +SKIP
            'hello'
            >>> lens(b'hello').decode_().set('world')  # doctest: +SKIP
            b'world'
        '''
        return self.add_lens(optics.DecodeIso(encoding, errors))

    def each_(self, filter_func=None, filter_none=False):
        '''A traversal that iterates over its state, focusing everything
        it iterates over. It uses `lenses.hooks.fromiter` to reform
        the state afterwards so it should work with any iterable that
        function supports. Analogous to `iter`.

            >>> from lenses import lens
            >>> data = [1, 2, 3]
            >>> lens().each_()
            Lens(None, EachTraversal())
            >>> lens(data).each_().get_all()
            [1, 2, 3]
            >>> lens(data).each_() + 1
            [2, 3, 4]
            >>> lens(data).each_(filter_none=True).set(None)
            []

        For technical reasons, this lens iterates over dictionaries by
        their items and not just their keys.

            >>> data = {'one': 1}
            >>> lens(data).each_().get_all()
            [('one', 1)]
            >>> lens(data).each_()[1] + 1
            {'one': 2}
        '''
        return self.add_lens(optics.EachTraversal(filter_func, filter_none))

    def error_(self, exception, message=None):
        '''An optic that raises an exception whenever it tries to focus
        something. If `message is None` then the exception will be
        raised unmodified. If `message is not None` then when the lens
        is asked to focus something it will run `message.format(state)`
        and the exception will be called with the resulting formatted
        message as it's only argument. Useful for debugging.

            >>> from lenses import lens
            >>> lens().error_(Exception())
            Lens(None, ErrorIso(Exception()))
            >>> lens().error_(Exception, '{}')
            Lens(None, ErrorIso(<...Exception...>, '{}'))
            >>> lens(True).error_(Exception).get()
            Traceback (most recent call last):
              File "<stdin>", line 1, in ?
            Exception
            >>> lens(True).error_(Exception('An error occurred')).set(False)
            Traceback (most recent call last):
              File "<stdin>", line 1, in ?
            Exception: An error occurred
            >>> lens(True).error_(ValueError, 'applied to {}').get()
            Traceback (most recent call last):
              File "<stdin>", line 1, in ?
            ValueError: applied to True
        '''
        return self.add_lens(optics.ErrorIso(exception, message))

    def f_(self, getter):
        '''An optic that wraps a getter function. A getter function is
        one that takes a state and returns a value derived from that
        state. The function is called on the focus before it is returned.

            >>> from lenses import lens
            >>> lens().f_(abs)
            Lens(None, Getter(<built-in function abs>))
            >>> lens(-1).f_(abs).get()
            1
            >>> lens([-1, 2, -3]).each_().f_(abs).get_all()
            [1, 2, 3]

        This optic cannot be used to set or modify values.
        '''
        return self.add_lens(optics.Getter(getter))

    def filter_(self, predicate):
        '''A prism that only focuses a value if the predicate returns
        `True` when called with that value as an argument. Best used
        when composed after a traversal. It only prevents the traversal
        from visiting foci, it does not filter out values the way that
        python's regular `filter` function does.

            >>> from lenses import lens
            >>> lens().filter_(all)
            Lens(None, FilteringPrism(<built-in function all>))
            >>> data = [[1, 2], [0], ['a'], ['', 'b']]
            >>> lens(data).each_().filter_(all).get_all()
            [[1, 2], ['a']]
            >>> lens(data).each_().filter_(all).set(2)
            [2, [0], 2, ['', 'b']]

        The filtering is done to foci before the lens' manipulation is
        applied. This means that the resulting foci can still violate
        the predicate if the manipulating function doesn't respect it:

            >>> lens(['', 2, '']).each_().filter_(bool).set(None)
            ['', None, '']
        '''
        return self.add_lens(optics.FilteringPrism(predicate))

    def fork_(self, *lenses):
        '''A setter representing the parallel composition of several
        sub-lenses.

            >>> from lenses import lens
            >>> lens().fork_(lens()[0], lens()[2])
            Lens(None, ForkedSetter(GetitemLens(0), GetitemLens(2)))
            >>> lens([[0, 0], 0, 0]).fork_(lens()[0][1], lens()[2]).set(1)
            [[0, 1], 0, 1]
        '''
        return self.add_lens(optics.ForkedSetter(*lenses))

    def get_(self, key, default=None):
        '''A lens that focuses an item inside a container by calling
        its `get` method, allowing you to specify a default value for
        missing keys.  Analogous to `dict.get`.

            >>> from lenses import lens
            >>> lens().get_('foo')
            Lens(None, GetitemOrElseLens('foo'))
            >>> lens({'foo': 'bar'}).get_('baz').get()
            >>> lens({'foo': 'bar'}).get_('baz', []).get()
            []
            >>> from collections import OrderedDict
            >>> lens(OrderedDict({'foo': 'bar'})).get_('baz').set('qux')
            OrderedDict([('foo', 'bar'), ('baz', 'qux')])
        '''
        return self.add_lens(optics.GetitemOrElseLens(key, default))

    def getattr_(self, name):
        '''A lens that focuses an attribute of an object. Analogous to
        `getattr`.

            >>> from lenses import lens
            >>> from collections import namedtuple
            >>> Pair = namedtuple('Pair', 'left right')
            >>> lens().getattr_('left')
            Lens(None, GetattrLens('left'))
            >>> lens(Pair(1, 2)).getattr_('left').get()
            1
            >>> lens(Pair(1, 2)).getattr_('right').set(3)
            Pair(left=1, right=3)
        '''
        return self.add_lens(optics.GetattrLens(name))

    def getitem_(self, key):
        '''A lens that focuses an item inside a container. Analogous to
        `operator.itemgetter`.

            >>> from lenses import lens
            >>> lens()[0]
            Lens(None, GetitemLens(0))
            >>> lens().getitem_(0)
            Lens(None, GetitemLens(0))
            >>> lens([1, 2, 3])[0].get()
            1
            >>> lens({'hello': 'world'})['hello'].get()
            'world'
            >>> lens([1, 2, 3])[0].set(4)
            [4, 2, 3]
            >>> lens({'hello': 'world'})['hello'].set('universe')
            {'hello': 'universe'}
        '''
        return self.add_lens(optics.GetitemLens(key))

    def getter_setter_(self, getter, setter):
        '''An optic that wraps a pair of getter and setter functions. A
        getter function is one that takes a state and returns a value
        derived from that state. A setter function takes an old state
        and a new value and uses them to construct a new state.

            >>> from lenses import lens
            >>> def getter(state):
            ...     'Get the average of a list'
            ...     return sum(state) // len(state)
            ...
            >>> def setter(old_state, value):
            ...     'Set the average of a list by changing the final value'
            ...     target_sum = value * len(old_state)
            ...     prefix = old_state[:-1]
            ...     return prefix + [target_sum - sum(prefix)]
            ...
            >>> average_lens = lens().getter_setter_(getter, setter)
            >>> average_lens
            Lens(None, Lens(<function getter...>, <function setter...>))
            >>> average_lens.bind([1, 2, 4, 5]).get()
            3
            >>> average_lens.bind([1, 2, 3]).set(4)
            [1, 2, 9]
            >>> average_lens.bind([1, 2, 3]) - 1
            [1, 2, 0]
        '''
        return self.add_lens(optics.Lens(getter, setter))

    def getzoomattr_(self, name):
        '''A traversal that focuses an attribute of an object, though if
        that attribute happens to be a lens it will zoom the lens. This
        is used internally to make lenses that are attributes of objects
        transparent. If you already know whether you are focusing a lens
        or a non-lens you should be explicit and use a ZoomAttrTraversal
        or a GetAttrLens respectively.

            >>> from lenses import lens
            >>> from collections import namedtuple
            >>> Triple = namedtuple('Triple', 'left mid right')
            >>> state = Triple(1, 2, lens().mid)
            >>> lens().left
            Lens(None, GetZoomAttrTraversal('left'))
            >>> lens(state).left.get()
            1
            >>> lens(state).left.set(3)
            Triple(left=3, mid=2, right=Lens(None, GetZoomAttrTraversal('mid')))
            >>> lens(state).right.get()
            2
            >>> lens(state).right.set(4)
            Triple(left=1, mid=4, right=Lens(None, GetZoomAttrTraversal('mid')))
        '''
        return self.add_lens(optics.GetZoomAttrTraversal(name))

    def instance_(self, type_):
        '''A prism that focuses a value only when that value is an
        instance of `type_`.

            >>> from lenses import lens
            >>> lens().instance_(int)
            Lens(None, InstancePrism(...))
            >>> lens(1).instance_(int).get_all()
            [1]
            >>> lens(1).instance_(float).get_all()
            []
            >>> lens(1).instance_(int).set(2)
            2
            >>> lens(1).instance_(float).set(2)
            1
        '''
        return self.add_lens(optics.InstancePrism(type_))

    def iso_(self, forwards, backwards):
        '''A lens based on an isomorphism. An isomorphism can be
        formed by two functions that mirror each other; they can convert
        forwards and backwards between a state and a focus without losing
        information. The difference between this and a regular Lens is
        that here the backwards functions don't need to know anything
        about the original state in order to produce a new state.

        These equalities should hold for the functions you supply (given
        a reasonable definition for __eq__):

            backwards(forwards(state)) == state
            forwards(backwards(focus)) == focus

        These kinds of conversion functions are very common across
        the python ecosystem. For example, NumPy has `np.array` and
        `np.ndarray.tolist` for converting between python lists and its
        own arrays. Isomorphism makes it easy to store data in one form,
        but interact with it in a more convenient form.

            >>> from lenses import lens
            >>> lens().iso_(chr, ord)
            Lens(None, Isomorphism(<... chr>, <... ord>))
            >>> lens(65).iso_(chr, ord).get()
            'A'
            >>> lens(65).iso_(chr, ord).set('B')
            66

        Due to their symmetry, isomorphisms can be flipped, thereby
        swapping thier forwards and backwards functions:

            >>> flipped = lens().iso_(chr, ord).flip()
            >>> flipped
            Lens(None, Isomorphism(<... ord>, <... chr>))
            >>> flipped.bind('A').get()
            65
        '''
        return self.add_lens(optics.Isomorphism(forwards, backwards))

    def item_(self, key):
        '''A lens that focuses a single item (key-value pair) in a
        dictionary by its key. Set an item to `None` to remove it from
        the dictionary.

            >>> from lenses import lens
            >>> from collections import OrderedDict
            >>> data = OrderedDict([(1, 10), (2, 20)])
            >>> lens().item_(1)
            Lens(None, ItemLens(1))
            >>> lens(data).item_(1).get()
            (1, 10)
            >>> lens(data).item_(3).get() is None
            True
            >>> lens(data).item_(1).set((1, 11))
            OrderedDict([(1, 11), (2, 20)])
            >>> lens(data).item_(1).set(None)
            OrderedDict([(2, 20)])
        '''
        return self.add_lens(optics.ItemLens(key))

    def item_by_value_(self, value):
        '''A lens that focuses a single item (key-value pair) in a
        dictionary by its value. Set an item to `None` to remove it
        from the dictionary. This lens assumes that there will only be
        a single key with that particular value. If you violate that
        assumption then you're on your own.

            >>> from lenses import lens
            >>> from collections import OrderedDict
            >>> data = OrderedDict([(1, 10), (2, 20)])
            >>> lens().item_by_value_(10)
            Lens(None, ItemByValueLens(10))
            >>> lens(data).item_by_value_(10).get()
            (1, 10)
            >>> lens(data).item_by_value_(30).get() is None
            True
            >>> lens(data).item_by_value_(10).set((3, 10))
            OrderedDict([(2, 20), (3, 10)])
            >>> lens(data).item_by_value_(10).set(None)
            OrderedDict([(2, 20)])
        '''
        return self.add_lens(optics.ItemByValueLens(value))

    def items_(self):
        '''A traversal focusing key-value tuples that are the items of
        a dictionary. Analogous to `dict.items`.

            >>> from lenses import lens
            >>> from collections import OrderedDict
            >>> data = OrderedDict([(1, 10), (2, 20)])
            >>> lens().items_()
            Lens(None, ItemsTraversal())
            >>> lens(data).items_().get_all()
            [(1, 10), (2, 20)]
            >>> lens(data).items_()[1].modify(lambda n: n + 1)
            OrderedDict([(1, 11), (2, 21)])
        '''
        return self.add_lens(optics.ItemsTraversal())

    def iter_(self):
        '''A fold that can get values from any iterable object in python
        by iterating over it. Like any fold, you cannot set values.

            >>> from lenses import lens
            >>> lens().iter_()
            Lens(None, IterableFold())
            >>> lens({2, 1, 3}).iter_().get_all()
            [1, 2, 3]
            >>> def numbers():
            ...     yield 1
            ...     yield 2
            ...     yield 3
            ...
            >>> lens(numbers()).iter_().get_all()
            [1, 2, 3]
            >>> lens([]).iter_().get_all()
            []

        If you want to be able to set values as you iterate then look
        into the EachTraversal.
        '''
        return self.add_lens(optics.IterableFold())

    def json_(self):
        '''An isomorphism that focuses a string containing json data as
        its parsed equivalent. Analogous to `json.loads`.

            >>> from lenses import lens
            >>> data = '[{"points": [4, 7]}]'
            >>> lens().json_()
            Lens(None, JsonIso())
            >>> lens(data).json_()[0]['points'][1].get()
            7
            >>> lens(data).json_()[0]['points'][0].set(8)
            '[{"points": [8, 7]}]'
        '''
        return self.add_lens(optics.JsonIso())

    def just_(self):
        '''A prism that focuses the value inside a `lenses.maybe.Just`
        object.

            >>> from lenses import lens
            >>> from lenses.maybe import Just, Nothing
            >>> lens().just_()
            Lens(None, JustPrism())
            >>> lens(Just(1)).just_().get_all()
            [1]
            >>> lens(Nothing()).just_().get_all()
            []
            >>> lens(Just(1)).just_().set(2)
            Just(2)
            >>> lens(Nothing()).just_().set(2)
            Nothing()
        '''
        return self.add_lens(optics.JustPrism())

    def keys_(self):
        '''A traversal focusing the keys of a dictionary. Analogous to
        `dict.keys`.

            >>> from lenses import lens
            >>> from collections import OrderedDict
            >>> data = OrderedDict([(1, 10), (2, 20)])
            >>> lens().keys_()
            Lens(None, KeysTraversal())
            >>> lens(data).keys_().get_all()
            [1, 2]
            >>> lens(data).keys_().modify(lambda n: n + 1)
            OrderedDict([(2, 10), (3, 20)])
        '''
        return self.add_lens(optics.KeysTraversal())

    def listwrap_(self):
        '''An isomorphism that wraps its state up in a list. This is
        occasionally useful when you need to make hetrogenous data more
        uniform. Analogous to `lambda state: [state]`.

            >>> from lenses import lens
            >>> lens().listwrap_()
            Lens(None, ListWrapIso())
            >>> lens(0).listwrap_().get()
            [0]
            >>> lens(0).listwrap_().set([1])
            1
            >>> l = lens().tuple_(lens()[0], lens()[1].listwrap_())
            >>> l.bind([[1, 3], 4]).each_().each_().get_all()
            [1, 3, 4]

        Also serves as an example that lenses do not always have to
        'zoom in' on a focus; they can also 'zoom out'.
        '''
        return self.add_lens(optics.ListWrapIso())

    def norm_(self, setter):
        '''An isomorphism that applies a function as it sets a new
        focus without regard to the old state. It will get foci without
        transformation. This lens allows you to pre-process values before
        you set them, but still get values as they exist in the state.
        Useful for type conversions or normalising data.

        For best results, your normalisation function should be
        idempotent.  That is, applying the function twice should have
        no effect:

            setter(setter(value)) == setter(value)

        Equivalent to `Isomorphism((lambda s: s), setter)`.

            >>> from lenses import lens
            >>> def real_only(num):
            ...     return num.real
            ...
            >>> lens().norm_(real_only)
            Lens(None, NormalisingIso(<function real_only at ...>))
            >>> lens([1.0, 2.0, 3.0])[0].norm_(real_only).get()
            1.0
            >>> lens([1.0, 2.0, 3.0])[0].norm_(real_only).set(4+7j)
            [4.0, 2.0, 3.0]

        Types with constructors that do conversion are often good targets
        for this lens:

            >>> lens([1, 2, 3])[0].norm_(int).set(4.0)
            [4, 2, 3]
            >>> lens([1, 2, 3])[1].norm_(int).set('5')
            [1, 5, 3]
        '''
        return self.add_lens(optics.NormalisingIso(setter))

    def prism_(self, unpack, pack):
        '''A prism is an optic made from a pair of functions that pack and
        unpack a state where the unpacking process can potentially fail.

        `pack` is a function that takes a focus and returns that focus
        wrapped up in a new state. `unpack` is a function that takes
        a state and unpacks it to get a focus. The unpack function
        must return an instance of `lenses.maybe.Maybe`; `Just` if the
        unpacking succeeded and `Nothing` if the unpacking failed.

        Parsing strings is a common situation when prisms are useful:

            >>> from lenses import lens
            >>> from lenses.maybe import Nothing, Just
            >>> def pack(focus):
            ...     return str(focus)
            ...
            >>> def unpack(state):
            ...     try:
            ...         return Just(int(state))
            ...     except ValueError:
            ...         return Nothing()
            ...
            >>> lens().prism_(unpack, pack)
            Lens(None, Prism(<function unpack ...>, <function pack ...>))
            >>> lens('42').prism_(unpack, pack).get_all()
            [42]
            >>> lens('fourty two').prism_(unpack, pack).get_all()
            []

        All prisms are also traversals that have exactly zero or one foci.
        '''
        return self.add_lens(optics.Prism(unpack, pack))

    def tuple_(self, *lenses):
        '''A lens that combines the focuses of other lenses into a
        single tuple. The sublenses must be optics of kind Lens; this
        means no Traversals.

            >>> from lenses import lens
            >>> lens().tuple_()
            Lens(None, TupleLens())
            >>> tl = lens().tuple_(lens()[0], lens()[2])
            >>> tl
            Lens(None, TupleLens(GetitemLens(0), GetitemLens(2)))
            >>> tl.bind([1, 2, 3, 4]).get()
            (1, 3)
            >>> tl.bind([1, 2, 3, 4]).set((5, 6))
            [5, 2, 6, 4]

        This lens is particularly useful when immediately followed by
        an EachLens, allowing you to traverse data even when it comes
        from disparate locations within the state.

            >>> state = ([1, 2, 3], 4, [5, 6])
            >>> tl.bind(state).each_().each_().get_all()
            [1, 2, 3, 5, 6]
            >>> tl.bind(state).each_().each_() + 10
            ([11, 12, 13], 4, [15, 16])
        '''
        return self.add_lens(optics.TupleLens(*lenses))

    def values_(self):
        '''A traversal focusing the values of a dictionary. Analogous to
        `dict.values`.

            >>> from lenses import lens
            >>> from collections import OrderedDict
            >>> data = OrderedDict([(1, 10), (2, 20)])
            >>> lens().values_()
            Lens(None, ValuesTraversal())
            >>> lens(data).values_().get_all()
            [10, 20]
            >>> lens(data).values_().modify(lambda n: n + 1)
            OrderedDict([(1, 11), (2, 21)])
        '''
        return self.add_lens(optics.ValuesTraversal())

    def zoom_(self):
        '''Follows its state as if it were a bound `Lens` object.

            >>> from lenses import lens
            >>> data = [lens([1, 2])[1], 4]
            >>> lens().zoom_()
            Lens(None, ZoomTraversal())
            >>> lens(data)[0].zoom_().get()
            2
            >>> lens(data)[0].zoom_().set(3)
            [[1, 3], 4]
        '''
        return self.add_lens(optics.ZoomTraversal())

    def zoomattr_(self, name):
        '''A lens that looks up an attribute on its target and follows
        it as if were a bound `Lens` object. Ignores the state, if any,
        of the lens that is being looked up.

            >>> from lenses import lens
            >>> class ClassWithLens(object):
            ...     def __init__(self, items):
            ...         self._private_items = items
            ...     def __repr__(self):
            ...         return 'ClassWithLens({!r})'.format(self._private_items)
            ...     first = lens()._private_items[0]
            ...
            >>> data = (ClassWithLens([1, 2, 3]), 4)
            >>> lens().zoomattr_('first')
            Lens(None, ZoomAttrTraversal('first'))
            >>> lens(data)[0].zoomattr_('first').get()
            1
            >>> lens(data)[0].zoomattr_('first').set(5)
            (ClassWithLens([5, 2, 3]), 4)
        '''
        return self.add_lens(optics.ZoomAttrTraversal(name))

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return self.bind(instance)

    def __getattr__(self, name):
        if name.endswith('_'):
            raise AttributeError('Not a valid lens constructor')

        if name.startswith('call_mut_'):
            def caller(*args, **kwargs):
                return self.call_mut(name[9:], *args, **kwargs)
            return caller

        if name.startswith('call_'):
            def caller(*args, **kwargs):
                return self.call(name[5:], *args, **kwargs)
            return caller

        return self.add_lens(optics.GetZoomAttrTraversal(name))

    def __getitem__(self, name):
        return self.add_lens(optics.GetitemLens(name))

    def _underlying_lens(self):
        return self.lens
