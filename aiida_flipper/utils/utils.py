# -*- coding: utf-8 -*-
"""Common utilities."""
from aiida import orm
import numpy as np
from matplotlib import pyplot as plt, gridspec
from scipy.stats import linregress

def get_or_create_input_node(cls, value, store=True):
    """Return a `Node` of a given class and given value.

    If a `Node` of the given type and value already exists, that will be returned, otherwise a new one will be created,
    stored and returned.

    :param cls: the `Node` class
    :param value: the value of the `Node`
    :param store: whether to store the new node
    
    check if we need other datatypes like arraydata
    """

    if cls in (orm.Bool, orm.Float, orm.Int, orm.Str):

        result = orm.QueryBuilder().append(cls, filters={'attributes.value': value}).first()

        if result is None:
            node = cls(value)
            if store:
                node = node.store()
        else:
            node = result[0]

    elif cls is orm.Dict:
        result = orm.QueryBuilder().append(cls, filters={'attributes': {'==': value}}).first()

        if result is None:
            node = cls(dict=value)
            if store:
                node = node.store()
        else:
            node = result[0]

    else:
        raise NotImplementedError

    return node

## Functions and Class used for fitting DFT and Pinball Forces 

def fit_with_lin_reg(f_exact, f_trial, traj_file=None, coefs=None, fit_forces=True, 
        fit_classical=False, verbosity=False, divide_r2=False, signal_indices=None):

    """
    :param list forces: a list of array that contains all the forces
        with shape nstep, nat, 3
    :param float coefs: a list of coefficient
    """
    
    for f in (f_exact, f_trial):
        assert isinstance(f, Force), "You have to pass an instance of {}".format(Force)

    if not( fit_forces or fit_classical) :
        raise Exception("Nothing to fit, specify --fit-forces or --fit-classical or both")

    # W is my exact value, this is where I am trying to get to by findding coefficients for each signal in f_trial
    W = f_exact.get_signal(0).flatten()
    signals = []

    if fit_forces:
        if signal_indices is None:
            signal_indices = range(1, f_trial.get_nr_of_signals())
        for i in signal_indices:
            signals.append(f_trial.get_signal(i).flatten())
    if fit_classical:
        from sklearn import linear_model
        from lib.produce_guesses import fittatraj
        alphas = []
        for alpha in np.arange(0.20, 1.80, 0.02):
            allgax = fittatraj(alpha, traj_file, nstep)
            newsignal = [allgax[i].flatten() for i in range(3)]
            clf = linear_model.LinearRegression()
            x = np.array(signal+newsignal).T
            clf.fit(x, W)
            coefs = clf.coef_
            alphas.append((clf._residues, alpha, clf.coef_))
        residue, alpha, coefs = sorted(alphas)[0]
    else:
        x = np.array(signals)
        xT = x.T
        coefs, sum_res, rank, s =  np.linalg.lstsq(xT, W, rcond=None)    #[0]  #+ 1.
        mae = np.sqrt(sum_res / len(W))
        r2 = 1.0 - sum_res / W.var() / len(W)
        if divide_r2:
            # m and r2 are the same here!
            r2 = 1. - sum_res / (W.size * W.var())
            coefs /= r2
    return coefs, mae

def make_fitted(f_trial, coefs, fit_forces=True, fit_classical=False, signal_indices=None):
    #~ print coefs, type(coefs)
    #~ raw_input()
    npoints, nsignals, ndim = f_trial.array.shape
    signals = []
    if fit_forces:
        if signal_indices is None:
            signal_indices = range(1, f_trial.get_nr_of_signals())
        for i in signal_indices:
            signals.append(f_trial.get_signal(i))
            # print f_trial.get_signal(i)[0]
    if fit_classical:
        allgax = fittatraj(alpha, traj_file, nstep)
        newsignal = [allgax[i] for i in range(3)]
        signal = signal + newsignal
    f_fitted = np.zeros((npoints, 3))
    assert len(coefs) == len(signals), "Incommensurate signals and coefficients"
    for i,coef in enumerate(coefs):
        f_fitted[:,:] += coef*signals[i]
    return Force(f_fitted)

def plot_forces(forces, format_=None, nrows=1,
        istart=0, iend=None, savefig=None, labels=None, titles=None,
        suptitle=None, filenames=None, common_limits=False, plot_fit=True,
        plot_slope1=False, plot_norm=False, limits=None, maxpoints=None):

    if format_ is None:
        format_ = ';'.join([
                "{}:0,{}:0".format(i,j)
                for i in range(len(forces))
                for j in range(i+1, len(forces))])

    format_list = format_.split(';')
    nr_of_plots = len(format_list)

    if titles:
        assert len(titles) == nr_of_plots, "Provide as many titles as plots"
    else:
        titles = format_list
    if labels:
        assert len(labels) == len(forces), "provide as many labels as files"
    else:
        labels = filenames

    minlen = min([len(f) for f in forces])
    if iend:
        minlen = min([minlen, iend])
    maxfor = max([f.get_maxforce() for f in forces])
    minfor = min([f.get_minforce() for f in forces])

    # Plotting everything to a row for now, this should be maybe changed at a later point:
    #~ fig = plt.figure(figsize=(10+nr_of_plots*5+1,10.5))
    #I = 0.8
    #fig = plt.figure(figsize=(4*I, 3*I))
    fig = plt.figure()
    if suptitle:
        plt.suptitle(suptitle, fontsize=12)
    gs = iter(gridspec.GridSpec(
            nrows, int(nr_of_plots/nrows+int(bool(nr_of_plots%nrows)))
     #       left=0.24, right=0.95, bottom=0.18, top=0.85
        ))

    for plot_index, form in enumerate(format_list):
        # Here I am expecting a list of fileindex1:format1, fileindex2:format2
        ax = fig.add_subplot(next(gs))
        ax.grid(color='grey', linestyle='--', linewidth=2, alpha=0.35)
        spec1, spec2 = form.split(',')
        f1_idx_str, form1 = spec1.split(':')
        f2_idx_str, form2 = spec2.split(':')
        f1_idx, f2_idx = int(f1_idx_str), int(f2_idx_str)
        f1 = forces[f1_idx]
        f2 = forces[f2_idx]
        signal_1 = f1.get_signal(form1)[:minlen]
        signal_2 = f2.get_signal(form2)[:minlen]
        X, Y = signal_1.reshape(minlen*3), signal_2.reshape(minlen*3)
        
        if plot_slope1:
            ax.plot([-absval, +absval], [-absval, +absval],color='grey', linestyle='--', linewidth=2, alpha=0.5)
        if maxpoints:
            indices = np.random.randint(0, minlen-1, maxpoints)
        for dim, c, colorlabel in zip(range(3), ('r','g', 'b'), ('X', 'Y', 'Z')):
            X_plot = signal_1[:, dim]
            Y_plot = signal_2[:, dim]
            if maxpoints:
                X_plot = X_plot[indices]
                Y_plot = Y_plot[indices]
            ax.scatter(X_plot, Y_plot,c=c, s=4, linewidth=0, label=colorlabel)
        if plot_norm:
            ax.scatter(np.linalg.norm(signal_1, axis=1), np.linalg.norm(signal_2, axis=1),c='black', s=8, linewidth=0, label='||f||')
        if limits:
            plt.ylim(*limits)
            plt.xlim(*limits)
            absval = max([abs(l) for l in limits])
        else:
            absval = max([abs(v) for v in (X.min(), X.max(), Y.min(), Y.max())])
            plt.ylim(-absval, +absval)
            plt.xlim(-absval, +absval)
        if plot_fit:
            slope, intercept, r_value, p_value, std_err = linregress(X,Y)
            ax.plot(
                    [-absval, absval],
                    [-absval*slope+intercept, absval*slope+intercept],
                    color='k', linestyle='--', 
                    linewidth=1,
                    #~ label=r'${:.3f}\pm{:.3f}$, $r^2 = {:.3f}$'.format(slope, std_err, r_value**2),
                    label=r'$r^2 = {:.2f}, m={:.2f}$'.format(r_value**2, slope),
                )
        #~ ax.plot([],[], label=r''.format(r_value**2), color='k', linestyle='--')
        plt.title(titles[plot_index])
        try:
            plt.xlabel(labels[f1_idx], fontsize=11)
            plt.ylabel(labels[f2_idx], fontsize=11)
        except:
            pass
        plt.legend(loc=2 if slope>0 else 1,fancybox=True, framealpha=0., scatterpoints=1, ncol=1, )

    if savefig is not None:
        plt.savefig(savefig)
    else:
        plt.show()
    return fig

class Force(object):
    """
    I basically store an array, ideally forces. I have some logic to get minimum and maximum values
    of the array.
    The main logic is in get_signal.
    """
    def __init__(self, arr, no_reshape=False):
        """
        :param arr: Of type numpy array (:todo: check).
        This array is then reshaped, into slices of 3, since we are in 3 dimension.
        If I get an array of shape 1000, 12, I assume I have collected 4 different forces,
        3 components for each, on 1000 points.
        Therefore, I reshape this array to 1000,4,3
        """
        if len(arr.shape) == 3:
            if no_reshape:
                # copy array as it is
                np, nsig, ncoord = arr.shape
                assert (ncoord == 3), "Third dimension of is not 3"
                ndim = nsig * 3
                self.array = arr
            else:
                # User did no flatten his array, I assume it is still nstep, nat, ndim
                nstep, nat, ndim = arr.shape
                assert (ndim % 3 == 0), "Number of columns is not multiple of 3"
                np = int(nstep*nat)
                self.array = arr.reshape((np, int(ndim/3), 3))
        elif len(arr.shape) == 2:
            np, ndim = arr.shape
            assert (ndim % 3 == 0), "Number of columns is not multiple of 3"
            # Here I reshape
            self.array = arr.reshape((np, int(ndim/3), 3))
        else:
            raise RuntimeError
        self.np = np
        self.ndim = ndim

    def __len__(self):
        return len(self.array)

    def get_nr_of_signals(self):
        return self.array.shape[1]

    def get_maxforce(self):
        """
        Get the maximum value I'm storing
        """
        i,j,k = np.unravel_index(self.array.argmax(), self.array.shape)
        return self.array[i,j,k]

    def get_minforce(self):
        """
        Get the minimum value I'm storing
        """
        i,j,k = np.unravel_index(self.array.argmin(), self.array.shape)
        return self.array[i,j,k]

    def get_signal(self, spec):
        """
        Here I can specify the form that I want.
        :param str form: Specification of the form
        The form specifies what I want.
        form="1" asks for the 1st signal, that is to the columns 4-6 that I passed.
        It is now also possible to ask for sums, i.e. form=0+4 (sums the 0th force to the fourth)s
        """
        if isinstance(spec, str):
            indices = [int(_) for _ in spec.split('+')]
        elif isinstance(spec,(tuple, list)):
            indices = spec
        elif isinstance(spec, int):
            indices = [spec]
        else:
            raise NotImplementedError
        to_return = np.zeros((self.np, 3))
        for idx in indices:
            to_return += self.array[:,idx,:]

        return to_return
